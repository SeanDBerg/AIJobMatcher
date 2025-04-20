# userLogin.py - Handles login/logout and demo mode toggle
from flask import Blueprint, request, redirect, url_for, flash, session
user_login_bp = Blueprint("user_login", __name__)
# === Manual user accounts ===
USER_ACCOUNTS = {
    "admin": "PerComp04!",
    "waifu": "creampie"
}
# === Routes ===
# POST /login - Enables full backend by setting authenticated session
@user_login_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    if username in USER_ACCOUNTS and USER_ACCOUNTS[username] == password:
        session["authenticated"] = True
        session["demo"] = False
        session["user_id"] = username  # ✅ Now dynamic
        flash(f"Login successful. Welcome, {username}!", "success")
    else:
        flash("Invalid credentials", "danger")

    return redirect(url_for("index"))


# GET /logout - Clears session and reverts to demo mode
@user_login_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out. Running in demo mode.", "info")
    return redirect(url_for("index"))
