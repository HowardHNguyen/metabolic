import test from "node:test";
import assert from "node:assert/strict";
import { parseLocation } from "../src/linkRoute.js";

test("new path-style email links carry the route and token without a fragment", () => {
  assert.deepEqual(parseLocation({ pathname: "/verify", search: "?token=abc_DEF-123", hash: "" }), { route: "verify", token: "abc_DEF-123" });
  assert.deepEqual(parseLocation({ pathname: "/reset", search: "?token=zzz", hash: "" }), { route: "reset", token: "zzz" });
  assert.equal(parseLocation({ pathname: "/signin", search: "", hash: "" }).route, "signin");
  assert.equal(parseLocation({ pathname: "/forgot/", search: "", hash: "" }).route, "forgot");
});

test("links already in inboxes (fragment form) keep working", () => {
  assert.deepEqual(parseLocation({ pathname: "/", search: "", hash: "#/verify?token=old123" }), { route: "verify", token: "old123" });
  assert.deepEqual(parseLocation({ pathname: "/", search: "", hash: "#/reset?token=old456" }), { route: "reset", token: "old456" });
});

test("ordinary navigation is unchanged", () => {
  assert.deepEqual(parseLocation({ pathname: "/", search: "", hash: "" }), { route: "landing", token: null });
  assert.deepEqual(parseLocation({ pathname: "/", search: "", hash: "#/signup" }), { route: "signup", token: null });
  assert.equal(parseLocation({ pathname: "/", search: "", hash: "#/assess" }).route, "assess");
});

test("a fragment-stripped link is the case that failed: no route and no token", () => {
  // what a mail app that drops '#...' used to deliver. With path links this can no longer happen for new emails.
  assert.deepEqual(parseLocation({ pathname: "/", search: "", hash: "" }), { route: "landing", token: null });
});

test("unknown paths and tokens-in-both-places do not break routing", () => {
  assert.equal(parseLocation({ pathname: "/whatever", search: "", hash: "" }).route, "landing");
  assert.equal(parseLocation({ pathname: "/verify", search: "?token=q", hash: "#/verify?token=h" }).token, "q");
});
