"""
Stripe billing integration for Notability AI Bridge.
Handles checkout sessions, webhook events, customer portal,
and plan upgrades/downgrades.

Required env vars:
  STRIPE_SECRET_KEY - sk_live_... or sk_test_...
  STRIPE_WEBHOOK_SECRET - whsec_... (from Stripe webhook settings)
  STRIPE_PRICE_PRO_MONTHLY - price_... (Pro plan monthly price ID)
  STRIPE_PRICE_TEAM_MONTHLY - price_... (Team plan monthly price ID)
  BASE_URL - https://your-app.up.railway.app
"""

import os
import json
import logging
import urllib.request
import urllib.parse

from database import get_user_by_id, get_user_by_api_key, update_user_plan

logger = logging.getLogger("notability-mcp-billing")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_TEAM = os.environ.get("STRIPE_PRICE_TEAM_MONTHLY", "")
BASE_URL = os.environ.get("BASE_URL", "")
STRIPE_API = "https://api.stripe.com/v1"
PLAN_PRICES = {"pro": STRIPE_PRICE_PRO, "team": STRIPE_PRICE_TEAM}


def _stripe_request(endpoint, data, method="POST"):
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY env var not set")
    encoded = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        f"{STRIPE_API}/{endpoint}",
        data=encoded if method == "POST" else None,
        method=method,
        headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"Stripe API error: {body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Stripe connection error: {e}")


def create_checkout_session(user_id, plan, api_key):
    price_id = PLAN_PRICES.get(plan)
    if not price_id:
        raise RuntimeError(f"No Stripe price configured for plan '{plan}'")
    user = get_user_by_id(user_id)
    if not user:
        raise RuntimeError("User not found")
    customer_id = user.get("stripe_customer_id", "")
    data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": f"{BASE_URL}/dashboard?key={api_key}&upgraded=1",
        "cancel_url": f"{BASE_URL}/dashboard?key={api_key}&upgraded=0",
        "metadata[user_id]": str(user_id),
        "metadata[api_key]": api_key,
        "metadata[plan]": plan,
        "client_reference_id": str(user_id),
    }
    if customer_id:
        data["customer"] = customer_id
    else:
        data["customer_email"] = user["email"]
    result = _stripe_request("checkout/sessions", data)
    return result.get("url", "")


def create_portal_session(customer_id, api_key):
    data = {"customer": customer_id, "return_url": f"{BASE_URL}/dashboard?key={api_key}"}
    result = _stripe_request("billing_portal/sessions", data)
    return result.get("url", "")


def handle_webhook(request_body, stripe_signature):
    event = _verify_and_construct_event(request_body, stripe_signature)
    if not event:
        return {"error": "Invalid signature"}
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    result = {"type": event_type}
    if event_type == "checkout.session.completed":
        user_id = int(data.get("metadata", {}).get("user_id", 0))
        plan = data.get("metadata", {}).get("plan", "")
        customer_id = data.get("customer", "")
        if user_id and plan:
            update_user_plan(user_id, plan, customer_id)
            result["action"] = f"Upgraded user {user_id} to {plan}"
        else:
            customer_email = data.get("customer_details", {}).get("email", "")
            if customer_email:
                from database import get_user_by_email
                user = get_user_by_email(customer_email)
                if user and plan:
                    update_user_plan(user["id"], plan, customer_id)
                    result["action"] = f"Upgraded {customer_email} to {plan}"
    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer", "")
        items = data.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id", "")
            plan = _price_to_plan(price_id)
            if plan:
                from database import get_conn
                with get_conn() as conn:
                    row = conn.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
                    if row:
                        update_user_plan(row["id"], plan, customer_id)
                        result["action"] = f"Updated user {row['id']} to {plan}"
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        from database import get_conn
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,)).fetchone()
            if row:
                update_user_plan(row["id"], "free", customer_id)
                result["action"] = f"Downgraded user {row['id']} to free"
    elif event_type == "invoice.paid":
        result["action"] = f"Payment received from {data.get('customer', '')}"
    elif event_type == "invoice.payment_failed":
        result["action"] = f"Payment failed for {data.get('customer', '')}"
    return result


def _verify_and_construct_event(body, signature):
    import hmac, hashlib, time as _time
    if not STRIPE_WEBHOOK_SECRET:
        return None
    try:
        elements = {}
        for item in signature.split(","):
            key, value = item.split("=", 1)
            elements[key] = value
        timestamp = elements.get("t", "")
        v1_signature = elements.get("v1", "")
        if not timestamp or not v1_signature:
            return None
        if int(_time.time()) - int(timestamp) > 300:
            return None
        signed_payload = f"{timestamp}.{body.decode()}".encode()
        expected_sig = hmac.new(STRIPE_WEBHOOK_SECRET.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, v1_signature):
            return None
        return json.loads(body.decode())
    except Exception:
        return None


def _price_to_plan(price_id):
    if price_id == STRIPE_PRICE_PRO:
        return "pro"
    elif price_id == STRIPE_PRICE_TEAM:
        return "team"
    return ""
