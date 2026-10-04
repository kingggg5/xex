<script lang="ts">
 let {initial}:{initial:string}=$props();
</script>
<svg viewBox="0 0 88 100" fill="none" aria-hidden="true">
 <defs><linearGradient id="portrait-metal" x2=".5" y2="1"><stop stop-color="#f2d59a"/><stop offset=".27" stop-color="#977447"/><stop offset=".6" stop-color="#55402c"/><stop offset="1" stop-color="#d7b270"/></linearGradient><radialGradient id="portrait-field" cx=".35" cy=".25"><stop stop-color="#3c607a"/><stop offset="1" stop-color="#0b182a"/></radialGradient></defs>
 <path d="M44 2 55 12l12 1 6 10 9 7-1 15 4 13-8 13-6 13-16 4-11 10-11-10-16-4-6-13-8-13 4-13-1-15 9-7 6-10 12-1Z" fill="#131c25" stroke="url(#portrait-metal)" stroke-width="2"/>
 <circle cx="44" cy="49" r="34" fill="url(#portrait-field)" stroke="url(#portrait-metal)" stroke-width="6"/>
 <circle cx="44" cy="49" r="28.5" stroke="#b4c4d4" stroke-opacity=".27"/>
 <path d="M12 29 5 24l1 14 7 9M76 29l7-5-1 14-7 9M14 65l-6 7 12 6 7-1m47-12 6 7-12 6-7-1" fill="#142638" stroke="url(#portrait-metal)" stroke-width="1.5"/>
 <path d="M22 77c4 7 10 9 17 8m27-8c-4 7-10 9-17 8M22 21c5-5 11-6 15-4m29 4c-5-5-11-6-15-4" stroke="#e0bf7b" stroke-width="1"/>
 <path d="M44 8c-3 5-8 9-15 9l7 5 8-3 8 3 7-5c-7 0-12-4-15-9ZM14 28c-5 11-5 27 1 36l4-6-3-10 3-11Zm60 0c5 11 5 27-1 36l-4-6 3-10-3-11Z" fill="url(#portrait-metal)" stroke="#322b24"/>
 <path d="m44 9 5 6-5 7-5-7Z" fill="#66c8ee" stroke="#cbdfdb"/>
 <path d="m44 74 7 8-7 9-7-9Z" fill="url(#portrait-metal)" stroke="#342a20"/><path d="m44 78 3 4-3 4-3-4Z" fill="#7dd6ee"/>
 <text x="44" y="59" text-anchor="middle" fill="#edf5ff" stroke="#061322" stroke-width="1.5" paint-order="stroke" font-family="Marcellus,serif" font-size="29">{initial}</text>
</svg>
