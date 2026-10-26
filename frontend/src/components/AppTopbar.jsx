import React from "react";

export default function AppTopbar({ email, onSignOut, onSignOutEverywhere, onHome, onAccount }) {
  return (
    <div className="app-topbar">
      <div className="shell">
        <button className="app-topbar-home" onClick={onHome}>
          ← Home
        </button>
        <div className="app-topbar-user">
          <span>
            Signed in as <strong>{email}</strong>
          </span>
          {onAccount && (
            <button className="app-topbar-signout" onClick={onAccount}>
              Change password
            </button>
          )}
          <button className="app-topbar-signout" onClick={onSignOut}>
            Sign out
          </button>
          <button className="app-topbar-signout" onClick={onSignOutEverywhere} title="Ends your session on every device">
            Sign out everywhere
          </button>
        </div>
      </div>
    </div>
  );
}
