//! OAuth sign-in for the login page (D-13): Google and Discord on top of the
//! existing anonymous session, with guest play as the zero-config default.
//!
//! Security posture:
//! - Confidential-client authorization-code flow with PKCE (S256); the client
//!   secret lives in environment variables only and is never logged.
//! - `state` is a random 32-byte token bound server-side to (provider, PKCE
//!   verifier) and mirrored in a `SameSite=Lax` cookie (top-level navigation
//!   back from the provider must carry it). Single use, 10-minute TTL, and the
//!   store is bounded.
//! - Access tokens are used once to fetch the provider identity and are then
//!   dropped; nothing about them is stored or logged.
//! - Redirect targets are fixed: only `{public_origin}/auth/{provider}/callback`
//!   is registered, and every failure returns to `/?login=<fixed reason>`.
//! - With no credentials configured, `/auth/providers` reports the provider
//!   disabled and `/start` redirects back with `login=provider_disabled`.

use std::{
    collections::{HashMap, VecDeque},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use axum::{
    Json, Router,
    extract::{Path, Query, State},
    http::{HeaderMap, HeaderValue, StatusCode, header::CACHE_CONTROL},
    response::{IntoResponse, Response},
    routing::get,
};
use base64url::base64url_nopad;
use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::auth::{
    AuthManager, AuthProvider, SESSION_TTL, SessionIdentity, cookie_value, encode_token_hex,
    random_session_token,
};

/// Login attempts are answered within this window or they are forgotten.
const ATTEMPT_TTL: Duration = Duration::from_secs(10 * 60);
/// Bounded state store (plan §12.4: counters stay finite).
const MAX_ATTEMPTS: usize = 1024;
const START_WINDOW: Duration = Duration::from_secs(60);
const MAX_STARTS_PER_WINDOW: usize = 30;
const HTTP_TIMEOUT: Duration = Duration::from_secs(5);
const STATE_COOKIE: &str = "aetherfield_oauth";

struct ProviderDef {
    id: &'static str,
    auth_url: &'static str,
    token_url: &'static str,
    user_url: &'static str,
    scope: &'static str,
}

const PROVIDERS: &[ProviderDef] = &[
    ProviderDef {
        id: "google",
        auth_url: "https://accounts.google.com/o/oauth2/v2/auth",
        token_url: "https://oauth2.googleapis.com/token",
        user_url: "https://openidconnect.googleapis.com/v1/userinfo",
        scope: "openid email profile",
    },
    ProviderDef {
        id: "discord",
        auth_url: "https://discord.com/oauth2/authorize",
        token_url: "https://discord.com/api/oauth2/token",
        user_url: "https://discord.com/api/v10/users/@me",
        scope: "identify",
    },
];

fn provider_def(id: &str) -> Option<&'static ProviderDef> {
    PROVIDERS.iter().find(|provider| provider.id == id)
}

#[derive(Clone)]
struct ProviderCredentials {
    client_id: String,
    client_secret: String,
}

/// Provider settings read from the environment at boot. Both providers start
/// disabled; the login page then offers guest play only.
#[derive(Clone, Default)]
pub struct OAuthSettings {
    public_origin: String,
    credentials: HashMap<&'static str, ProviderCredentials>,
}

impl OAuthSettings {
    /// Reads `AETHERFIELD_GOOGLE_CLIENT_ID`/`_SECRET`,
    /// `AETHERFIELD_DISCORD_CLIENT_ID`/`_SECRET` and `AETHERFIELD_PUBLIC_ORIGIN`
    /// (the browser origin players use; it must match the server's allowed
    /// Origin). Injected lookup keeps tests free of process-wide env races.
    pub fn from_env() -> Self {
        Self::from_lookup(|key| {
            std::env::var(key)
                .ok()
                .map(|value| value.trim().to_string())
        })
    }

    pub fn from_lookup(get: impl Fn(&str) -> Option<String>) -> Self {
        let mut credentials = HashMap::new();
        for provider in PROVIDERS {
            let Some(client_id) = non_empty(get(&format!(
                "AETHERFIELD_{}_CLIENT_ID",
                provider.id.to_uppercase()
            ))) else {
                continue;
            };
            let Some(client_secret) = non_empty(get(&format!(
                "AETHERFIELD_{}_CLIENT_SECRET",
                provider.id.to_uppercase()
            ))) else {
                continue;
            };
            credentials.insert(
                provider.id,
                ProviderCredentials {
                    client_id,
                    client_secret,
                },
            );
        }
        Self {
            public_origin: non_empty(get("AETHERFIELD_PUBLIC_ORIGIN"))
                .unwrap_or_else(|| "http://127.0.0.1:5173".to_string()),
            credentials,
        }
    }

    pub fn provider_enabled(&self, id: &str) -> bool {
        self.credentials.contains_key(id)
    }

    fn callback_url(&self, id: &str) -> String {
        format!("{}/auth/{id}/callback", self.public_origin)
    }

    fn secure_cookies(&self) -> bool {
        self.public_origin.starts_with("https://")
    }
}

fn non_empty(value: Option<String>) -> Option<String> {
    value.filter(|value| !value.is_empty())
}

struct OAuthAttempt {
    provider: &'static str,
    verifier: String,
    expires_at: Instant,
}

/// Everything the OAuth routes need. The auth manager is shared with the rest
/// of the server so an OAuth callback upgrades the browser's existing session
/// instead of forking a second one.
pub struct OAuthContext {
    settings: OAuthSettings,
    auth: Arc<tokio::sync::Mutex<AuthManager>>,
    attempts: Mutex<HashMap<String, OAuthAttempt>>,
    starts: Mutex<VecDeque<Instant>>,
    http: reqwest::Client,
    /// Durable storage (V5-12): the callback links the provider subject onto
    /// the browser's principal so a second device lands on the same character.
    storage: crate::storage::StorageHandle,
}

impl OAuthContext {
    pub fn new(settings: OAuthSettings, auth: Arc<tokio::sync::Mutex<AuthManager>>) -> Self {
        Self::new_with_storage(settings, auth, crate::storage::StorageHandle::disabled())
    }

    pub fn new_with_storage(
        settings: OAuthSettings,
        auth: Arc<tokio::sync::Mutex<AuthManager>>,
        storage: crate::storage::StorageHandle,
    ) -> Self {
        let http = reqwest::Client::builder()
            .timeout(HTTP_TIMEOUT)
            .https_only(true)
            .build()
            .unwrap_or_default();
        Self {
            settings,
            auth,
            attempts: Mutex::new(HashMap::new()),
            starts: Mutex::new(VecDeque::new()),
            http,
            storage,
        }
    }

    pub fn provider_enabled(&self, id: &str) -> bool {
        self.settings.provider_enabled(id)
    }

    fn begin_attempt(&self, provider: &'static str) -> Option<(String, String)> {
        let now = Instant::now();
        let mut starts = self.starts.lock().expect("oauth start limiter");
        while starts
            .front()
            .is_some_and(|at| now.saturating_duration_since(*at) >= START_WINDOW)
        {
            starts.pop_front();
        }
        if starts.len() >= MAX_STARTS_PER_WINDOW {
            return None;
        }
        starts.push_back(now);
        drop(starts);

        let state = encode_token_hex(&random_session_token().ok()?);
        let verifier = encode_token_hex(&random_session_token().ok()?);
        let mut attempts = self.attempts.lock().expect("oauth attempt store");
        attempts.retain(|_, attempt| attempt.expires_at > now);
        if attempts.len() >= MAX_ATTEMPTS {
            return None;
        }
        attempts.insert(
            state.clone(),
            OAuthAttempt {
                provider,
                verifier: verifier.clone(),
                expires_at: now + ATTEMPT_TTL,
            },
        );
        Some((state, verifier))
    }

    /// Single-use consume; the provider must match the one that started it.
    fn take_attempt(&self, state: &str, provider: &str) -> Option<String> {
        let now = Instant::now();
        let mut attempts = self.attempts.lock().expect("oauth attempt store");
        let attempt = attempts.remove(state)?;
        (attempt.provider == provider && attempt.expires_at > now).then_some(attempt.verifier)
    }
}

/// Merge into the application router after `with_state` (this router carries
/// its own state).
pub fn router(context: Arc<OAuthContext>) -> Router<()> {
    Router::new()
        .route("/auth/providers", get(providers_handler))
        .route("/auth/{provider}/start", get(start_handler))
        .route("/auth/{provider}/callback", get(callback_handler))
        .with_state(context)
}

#[derive(serde::Serialize)]
struct ProvidersResponse {
    google: bool,
    discord: bool,
}

async fn providers_handler(
    State(context): State<Arc<OAuthContext>>,
    headers: HeaderMap,
) -> Response {
    // Fetch endpoint (our client only): require the exact Origin, like /session.
    if !origin_is_required(&headers) {
        return no_store(StatusCode::FORBIDDEN, "origin_denied");
    }
    let response = Json(ProvidersResponse {
        google: context.settings.provider_enabled("google"),
        discord: context.settings.provider_enabled("discord"),
    });
    with_no_store(response.into_response())
}

async fn start_handler(
    State(context): State<Arc<OAuthContext>>,
    Path(provider_id): Path<String>,
    headers: HeaderMap,
) -> Response {
    if !origin_header_allowed(&headers) {
        return no_store(StatusCode::FORBIDDEN, "origin_denied");
    }
    let Some(provider) = provider_def(&provider_id) else {
        return error_redirect("unknown_provider");
    };
    let Some(credentials) = context.settings.credentials.get(provider.id) else {
        return error_redirect("provider_disabled");
    };
    let Some((state, verifier)) = context.begin_attempt(provider.id) else {
        return error_redirect("rate_limited");
    };
    let url = build_authorization_url(provider, credentials, &context.settings, &state, &verifier);
    let cookie = format!(
        "{STATE_COOKIE}={state}; HttpOnly; SameSite=Lax; Path=/auth; Max-Age={}{redirect}",
        ATTEMPT_TTL.as_secs(),
        redirect = secure_suffix(context.settings.secure_cookies()),
    );
    let mut response = StatusCode::FOUND.into_response();
    set_header(&mut response, axum::http::header::LOCATION, &url);
    set_header(&mut response, axum::http::header::SET_COOKIE, &cookie);
    with_no_store(response)
}

#[derive(Deserialize)]
struct CallbackParams {
    code: Option<String>,
    state: Option<String>,
    error: Option<String>,
}

async fn callback_handler(
    State(context): State<Arc<OAuthContext>>,
    Path(provider_id): Path<String>,
    Query(params): Query<CallbackParams>,
    headers: HeaderMap,
) -> Response {
    let clear_state_cookie =
        format!("{STATE_COOKIE}=; HttpOnly; SameSite=Lax; Path=/auth; Max-Age=0");
    let finish = |location: &str, session_cookie: Option<String>| {
        let mut response = StatusCode::FOUND.into_response();
        set_header(&mut response, axum::http::header::LOCATION, location);
        set_header(
            &mut response,
            axum::http::header::SET_COOKIE,
            &clear_state_cookie,
        );
        if let Some(session_cookie) = session_cookie {
            set_header(
                &mut response,
                axum::http::header::SET_COOKIE,
                &session_cookie,
            );
        }
        with_no_store(response)
    };

    let Some(provider) = provider_def(&provider_id) else {
        return finish("/?login=unknown_provider", None);
    };
    // Double-submit CSRF check: the state in the URL must be the one this
    // server issued in the cookie for this exact provider.
    let query_state = params.state.as_deref().unwrap_or_default();
    let cookie_state = cookie_value(
        headers
            .get(axum::http::header::COOKIE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default(),
        STATE_COOKIE,
    )
    .unwrap_or_default();
    let verifier = if query_state.is_empty() || query_state != cookie_state {
        None
    } else {
        context.take_attempt(query_state, provider.id)
    };
    let Some(verifier) = verifier else {
        return finish("/?login=state", None);
    };
    if params.error.is_some() {
        return finish("/?login=denied", None);
    }
    let Some(code) = params
        .code
        .as_deref()
        .filter(|code| !code.is_empty() && code.len() <= 512)
    else {
        return finish("/?login=exchange", None);
    };
    let Some(credentials) = context.settings.credentials.get(provider.id) else {
        return finish("/?login=provider_disabled", None);
    };

    let identity = match exchange_code_for_identity(
        &context.http,
        provider,
        credentials,
        &context.settings,
        code,
        &verifier,
    )
    .await
    {
        Ok(identity) => identity,
        Err(_) => return finish("/?login=exchange", None),
    };
    let identity_subject = identity.subject.clone();
    // Never bind a session to a dangling identity: the sanitizer empties an
    // unusable provider subject instead of mangling it.
    if identity.subject.is_empty() {
        return finish("/?login=exchange", None);
    }

    // SameSite=Lax on the session cookie (changed from Strict for D-13) so the
    // browser's existing session rides along on the provider's top-level
    // navigation back; cross-site POSTs stay cookieless as before.
    let existing = session_from_headers(&headers);
    let session_id = match context.auth.lock().await.create_or_refresh_session(
        existing,
        identity,
        Instant::now(),
    ) {
        Ok(session_id) => session_id,
        Err(_) => return finish("/?login=capacity", None),
    };
    let session_cookie = format!(
        "aetherfield_session={}; HttpOnly; SameSite=Lax; Path=/; Max-Age={}{redirect}",
        encode_token_hex(&session_id),
        SESSION_TTL.as_secs(),
        redirect = secure_suffix(context.settings.secure_cookies()),
    );
    // V5-12: the provider identity becomes durable. The browser's principal
    // (minted on the spot when the cookie is missing) claims the subject; a
    // subject that already belongs to another principal adopts that one, so
    // a second device lands on the same character.
    let principal_token = crate::auth::decode_session_cookie(
        headers
            .get(axum::http::header::COOKIE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or(""),
        crate::storage::PRINCIPAL_COOKIE_NAME,
    )
    .map(|token| crate::auth::encode_token_hex(&token));
    let principal_token = match principal_token {
        Some(token) => token,
        None => match crate::auth::random_session_token() {
            Ok(token) => crate::auth::encode_token_hex(&token),
            Err(_) => return finish("/?login=capacity", None),
        },
    };
    let principal = match context.storage.ensure_principal(&principal_token).await {
        Ok(principal) => principal,
        Err(_) => return finish("/?login=capacity", None),
    };
    let principal = match context
        .storage
        .link_principal(principal, provider.id, Some(&identity_subject))
        .await
    {
        Ok(crate::storage::LinkOutcome::Linked) => principal,
        Ok(crate::storage::LinkOutcome::Adopted(other)) => other,
        Err(_) => return finish("/?login=capacity", None),
    };
    if context
        .auth
        .lock()
        .await
        .set_principal(session_id, principal, Instant::now())
        .is_err()
    {
        return finish("/?login=capacity", None);
    }
    // The principal cookie is refreshed here too: a login is a top-level
    // navigation, so this is the one place a fresh browser gains the
    // durable identity cookie.
    let principal_set_cookie = format!(
        "{}={}; HttpOnly; SameSite=Lax; Path=/; Max-Age={}{redirect}",
        crate::storage::PRINCIPAL_COOKIE_NAME,
        principal_token,
        crate::storage::PRINCIPAL_TTL_SECS,
        redirect = secure_suffix(context.settings.secure_cookies()),
    );
    let mut response = StatusCode::FOUND.into_response();
    set_header(&mut response, axum::http::header::LOCATION, "/");
    set_header(
        &mut response,
        axum::http::header::SET_COOKIE,
        &clear_state_cookie,
    );
    set_header(
        &mut response,
        axum::http::header::SET_COOKIE,
        &session_cookie,
    );
    set_header(
        &mut response,
        axum::http::header::SET_COOKIE,
        &principal_set_cookie,
    );
    with_no_store(response)
}

fn build_authorization_url(
    provider: &ProviderDef,
    credentials: &ProviderCredentials,
    settings: &OAuthSettings,
    state: &str,
    verifier: &str,
) -> String {
    let challenge = base64url_nopad(&Sha256::digest(verifier.as_bytes()));
    let mut url = reqwest::Url::parse(provider.auth_url).expect("provider auth URL is a valid URL");
    url.query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &credentials.client_id)
        .append_pair("redirect_uri", &settings.callback_url(provider.id))
        .append_pair("scope", provider.scope)
        .append_pair("state", state)
        .append_pair("code_challenge", &challenge)
        .append_pair("code_challenge_method", "S256");
    url.into()
}

#[derive(Deserialize)]
struct TokenResponse {
    access_token: Option<String>,
}

#[derive(Deserialize)]
struct GoogleUser {
    sub: Option<String>,
    name: Option<String>,
}

#[derive(Deserialize)]
struct DiscordUser {
    id: Option<String>,
    username: Option<String>,
    global_name: Option<String>,
}

async fn exchange_code_for_identity(
    http: &reqwest::Client,
    provider: &ProviderDef,
    credentials: &ProviderCredentials,
    settings: &OAuthSettings,
    code: &str,
    verifier: &str,
) -> Result<SessionIdentity, ()> {
    let token: TokenResponse = http
        .post(provider.token_url)
        .header(reqwest::header::ACCEPT, "application/json")
        .form(&[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("redirect_uri", &settings.callback_url(provider.id)),
            ("client_id", credentials.client_id.as_str()),
            ("client_secret", credentials.client_secret.as_str()),
            ("code_verifier", verifier),
        ])
        .send()
        .await
        .map_err(|_| ())?
        .error_for_status()
        .map_err(|_| ())?
        .json()
        .await
        .map_err(|_| ())?;
    let Some(access_token) = token.access_token.filter(|token| !token.is_empty()) else {
        return Err(());
    };

    let raw = http
        .get(provider.user_url)
        .bearer_auth(&access_token)
        .send()
        .await
        .map_err(|_| ())?
        .error_for_status()
        .map_err(|_| ())?
        .text()
        .await
        .map_err(|_| ())?;
    // The token is dropped here; only the identity survives.
    match provider.id {
        "google" => {
            let user: GoogleUser = serde_json::from_str(&raw).map_err(|_| ())?;
            Ok(SessionIdentity::new(
                AuthProvider::Google,
                &user.sub.unwrap_or_default(),
                &user.name.unwrap_or_default(),
            ))
        }
        "discord" => {
            let user: DiscordUser = serde_json::from_str(&raw).map_err(|_| ())?;
            let name = user
                .global_name
                .unwrap_or_else(|| user.username.clone().unwrap_or_default());
            Ok(SessionIdentity::new(
                AuthProvider::Discord,
                &user.id.unwrap_or_default(),
                &name,
            ))
        }
        _ => Err(()),
    }
}

/// Navigations may omit Origin; if the browser did send one it must be the
/// game origin (same rule as the fetch endpoints, minus the mandatory part).
/// Fetch endpoints accept a MISSING Origin (browsers omit it on same-origin
/// GETs, and GETs carry no CSRF risk), but a present Origin must be exactly
/// the game origin — cross-site fetches always send one, so foreign pages
/// stay blocked. Navigations may omit Origin for the same reason.
fn origin_is_required(headers: &HeaderMap) -> bool {
    match headers
        .get(axum::http::header::ORIGIN)
        .and_then(|value| value.to_str().ok())
    {
        None => true,
        Some(origin) => origin == crate::auth::allowed_origin(),
    }
}

fn origin_header_allowed(headers: &HeaderMap) -> bool {
    headers
        .get(axum::http::header::ORIGIN)
        .and_then(|value| value.to_str().ok())
        .map(|origin| origin == crate::auth::allowed_origin())
        .unwrap_or(true)
}

fn session_from_headers(headers: &HeaderMap) -> Option<crate::auth::SessionId> {
    let cookie = headers.get(axum::http::header::COOKIE)?.to_str().ok()?;
    crate::auth::decode_session_cookie(cookie, "aetherfield_session")
}

fn error_redirect(reason: &'static str) -> Response {
    let mut response = StatusCode::FOUND.into_response();
    set_header(
        &mut response,
        axum::http::header::LOCATION,
        &format!("/?login={reason}"),
    );
    with_no_store(response)
}

fn secure_suffix(secure: bool) -> &'static str {
    if secure { "; Secure" } else { "" }
}

fn set_header(response: &mut Response, name: axum::http::HeaderName, value: &str) {
    if let Ok(header_value) = HeaderValue::from_str(value) {
        response.headers_mut().append(name, header_value);
    }
}

fn with_no_store(response: Response) -> Response {
    let mut response = response;
    response
        .headers_mut()
        .insert(CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

fn no_store(status: StatusCode, message: &'static str) -> Response {
    with_no_store((status, message).into_response())
}

pub mod base64url {
    /// URL-safe base64 without padding (RFC 4648 §5), as PKCE requires.
    pub fn base64url_nopad(data: &[u8]) -> String {
        const ALPHABET: &[u8; 64] =
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
        let mut encoded = String::with_capacity(data.len().div_ceil(3) * 4);
        for chunk in data.chunks(3) {
            let buffer = [
                chunk[0],
                *chunk.get(1).unwrap_or(&0),
                *chunk.get(2).unwrap_or(&0),
            ];
            let bits =
                (u32::from(buffer[0]) << 16) | (u32::from(buffer[1]) << 8) | u32::from(buffer[2]);
            let needed = match chunk.len() {
                1 => 2,
                2 => 3,
                _ => 4,
            };
            for index in 0..needed {
                encoded.push(ALPHABET[(bits >> (18 - index * 6)) as usize & 0x3f] as char);
            }
        }
        encoded
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::AuthManager;

    fn settings_with_google() -> OAuthSettings {
        OAuthSettings::from_lookup(|key| match key {
            "AETHERFIELD_GOOGLE_CLIENT_ID" => Some("google-client-id".to_string()),
            "AETHERFIELD_GOOGLE_CLIENT_SECRET" => Some("google-client-secret".to_string()),
            "AETHERFIELD_PUBLIC_ORIGIN" => Some("http://127.0.0.1:5173".to_string()),
            _ => None,
        })
    }

    #[test]
    fn providers_stay_disabled_without_credentials() {
        let settings = OAuthSettings::from_lookup(|_| None);
        assert_eq!(settings.public_origin, "http://127.0.0.1:5173");
        assert!(!settings.provider_enabled("google"));
        assert!(!settings.provider_enabled("discord"));

        let settings = settings_with_google();
        assert!(settings.provider_enabled("google"));
        assert!(!settings.provider_enabled("discord"));
        assert_eq!(
            settings.callback_url("google"),
            "http://127.0.0.1:5173/auth/google/callback"
        );
    }

    #[test]
    fn authorization_url_carries_pkce_and_state() {
        let settings = settings_with_google();
        let provider = provider_def("google").unwrap();
        let credentials = settings.credentials.get("google").unwrap();
        let url = build_authorization_url(
            provider,
            credentials,
            &settings,
            "state-token",
            "verifier-token",
        );
        assert!(url.starts_with("https://accounts.google.com/o/oauth2/v2/auth?"));
        assert!(url.contains("client_id=google-client-id"));
        assert!(
            url.contains("redirect_uri=http%3A%2F%2F127.0.0.1%3A5173%2Fauth%2Fgoogle%2Fcallback")
        );
        assert!(url.contains("scope=openid+email+profile"));
        assert!(url.contains("state=state-token"));
        assert!(url.contains("code_challenge_method=S256"));
        // sha256("verifier-token"), base64url without padding.
        let expected = base64url_nopad(&Sha256::digest(b"verifier-token"));
        assert!(url.contains(&format!("code_challenge={expected}")));
    }

    #[test]
    fn base64url_matches_known_vectors() {
        // RFC 4648 test vectors, URL-safe without padding.
        assert_eq!(base64url_nopad(b""), "");
        assert_eq!(base64url_nopad(b"f"), "Zg");
        assert_eq!(base64url_nopad(b"fo"), "Zm8");
        assert_eq!(base64url_nopad(b"foo"), "Zm9v");
        assert_eq!(base64url_nopad(b"foob"), "Zm9vYg");
        assert_eq!(base64url_nopad(b"fooba"), "Zm9vYmE");
        assert_eq!(base64url_nopad(b"foobar"), "Zm9vYmFy");
        // Standard-alphabet fixtures translate to the URL-safe alphabet.
        assert_eq!(base64url_nopad(&[0xfb, 0xff]), "-_8");
        assert_eq!(base64url_nopad(&[0xff, 0xfb]), "__s");
    }

    #[test]
    fn attempts_are_single_use_bound_and_expire() {
        let context = OAuthContext::new(
            settings_with_google(),
            Arc::new(tokio::sync::Mutex::new(AuthManager::default())),
        );
        let (state, verifier) = context.begin_attempt("google").expect("attempt stored");
        assert_eq!(
            context.take_attempt(&state, "google").as_deref(),
            Some(verifier.as_str())
        );
        assert_eq!(
            context.take_attempt(&state, "google"),
            None,
            "state must be single use"
        );

        let (state, _) = context.begin_attempt("google").unwrap();
        assert_eq!(
            context.take_attempt(&state, "discord"),
            None,
            "state is provider-bound"
        );
        assert_eq!(
            context.take_attempt(&state, "google"),
            None,
            "consumed even on provider mismatch"
        );

        let (state, _) = context.begin_attempt("google").unwrap();
        // Expired attempts are refused rather than replayed.
        {
            let mut attempts = context.attempts.lock().unwrap();
            if let Some(attempt) = attempts.get_mut(&state) {
                attempt.expires_at = Instant::now() - Duration::from_secs(1);
            }
        }
        assert_eq!(context.take_attempt(&state, "google"), None);
    }

    #[test]
    fn unknown_state_is_rejected() {
        let context = OAuthContext::new(
            settings_with_google(),
            Arc::new(tokio::sync::Mutex::new(AuthManager::default())),
        );
        assert_eq!(context.take_attempt("never-issued", "google"), None);
    }

    #[test]
    fn start_limiter_is_bounded_per_window() {
        let context = OAuthContext::new(
            settings_with_google(),
            Arc::new(tokio::sync::Mutex::new(AuthManager::default())),
        );
        for _ in 0..MAX_STARTS_PER_WINDOW {
            assert!(context.begin_attempt("google").is_some());
        }
        assert!(
            context.begin_attempt("google").is_none(),
            "the window must cap starts"
        );
    }

    #[test]
    fn attempt_store_stays_bounded() {
        let context = OAuthContext::new(
            settings_with_google(),
            Arc::new(tokio::sync::Mutex::new(AuthManager::default())),
        );
        for _ in 0..(MAX_ATTEMPTS + 10) {
            // When full, new attempts are refused rather than growing memory.
            let _ = context.begin_attempt("google");
        }
        assert!(context.attempts.lock().unwrap().len() <= MAX_ATTEMPTS);
    }

    #[test]
    fn origin_navigation_without_header_is_allowed_but_foreign_is_not() {
        let mut headers = HeaderMap::new();
        assert!(origin_header_allowed(&headers));
        assert!(
            origin_is_required(&headers),
            "a same-origin GET may omit Origin; cross-site fetches always send one"
        );
        headers.insert(
            axum::http::header::ORIGIN,
            HeaderValue::from_static("http://evil.example"),
        );
        assert!(!origin_header_allowed(&headers));
        headers.insert(
            axum::http::header::ORIGIN,
            HeaderValue::from_static("http://127.0.0.1:5173"),
        );
        assert!(origin_header_allowed(&headers));
    }

    #[test]
    fn identity_mapping_sanitizes_provider_names() {
        let identity = SessionIdentity::new(
            AuthProvider::Discord,
            "123456789012345678",
            "  Speaker\u{0007}of\u{0009}Winds  ",
        );
        assert_eq!(identity.display_name, "Speaker of Winds");
        let identity = SessionIdentity::new(AuthProvider::Google, "sub-ject_01", "\u{2028}\u{0}");
        assert_eq!(
            identity.display_name, "Traveler",
            "an empty name falls back"
        );
        let identity = SessionIdentity::new(
            AuthProvider::Google,
            "bad subject!",
            "x".repeat(64).as_str(),
        );
        assert_eq!(identity.subject, "", "an invalid subject never ships");
        assert_eq!(
            identity.display_name.chars().count(),
            32,
            "names are capped"
        );
    }
}
