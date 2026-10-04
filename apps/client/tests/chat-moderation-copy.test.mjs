import { test } from "node:test";
import assert from "node:assert/strict";
import { chatModerationText } from "../src/chat-moderation-copy.mjs";

test("all server moderation reasons explain withholding in Thai and English", () => {
    for (const key of ["chat_review_required", "chat_invalid_message", "chat_rate_limited", "chat_duplicate", "chat_unavailable"]) {
        assert.match(chatModerationText(key,"en"), /[a-z]/i);
        assert.match(chatModerationText(key,"th"), /[ก-๙]/);
    }
});
test("unknown server data and prototype keys never become messages", () => {
    for (const key of [null,{},"constructor","__proto__","raw private text","group_full"]) assert.equal(chatModerationText(key,"en"),null);
});
