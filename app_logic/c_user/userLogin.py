# userLogin.py - Handles login/logout and demo mode toggle
from flask import Blueprint, request, redirect, url_for, flash, session

user_login_bp = Blueprint("user_login", __name__)

# POST /login - Enables full backend by setting authenticated session
@user_login_bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    if username == "admin" and password == "password":
        session["authenticated"] = True
        session["demo"] = False
        flash("Login successful", "success")
    else:
        flash("Invalid credentials", "danger")

    return redirect(url_for("index"))

# GET /logout - Clears session and reverts to demo mode
@user_login_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out. Running in demo mode.", "info")
    return redirect(url_for("index"))
