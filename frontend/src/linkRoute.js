// Where is the user and which email-link token (if any) came with them?
//
// New email links are plain paths: https://host/verify?token=...  (some mail apps and in-app browsers drop everything
// after a "#", which sent users to the start page with their token lost). Links already in people's inboxes use the
// old fragment form, https://host/#/verify?token=..., and keep working.
export const ROUTES = ["signup", "signin", "assess", "forgot", "reset", "verify", "account"];

export function parseLocation({ pathname = "/", search = "", hash = "" } = {}) {
  const [hashRoute, hashQuery = ""] = hash.replace(/^#\/?/, "").split("?");
  const pathRoute = pathname.replace(/^\/+|\/+$/g, "");
  const route = ROUTES.includes(hashRoute) ? hashRoute : ROUTES.includes(pathRoute) ? pathRoute : "landing";
  const token = new URLSearchParams(search).get("token") || new URLSearchParams(hashQuery).get("token") || null;
  return { route, token };
}
