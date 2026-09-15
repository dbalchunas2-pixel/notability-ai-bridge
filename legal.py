"""Legal page HTML for Notability AI Bridge."""

PRIVACY_HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Privacy Policy - Notability AI Bridge</title>
<style>
:root { --bg: #0f1117; --text: #e4e4e7; --muted: #71717a; --accent: #6366f1; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }
.container { max-width: 720px; margin: 0 auto; padding: 60px 24px; }
h1 { font-size: 2rem; margin-bottom: 8px; }
.updated { color: var(--muted); font-size: 0.9rem; margin-bottom: 40px; }
h2 { font-size: 1.3rem; margin-top: 36px; margin-bottom: 12px; color: #a5b4fc; }
p { margin-bottom: 16px; }
ul { margin-bottom: 16px; padding-left: 24px; }
li { margin-bottom: 8px; }
a { color: var(--accent); }
.footer { margin-top: 60px; padding-top: 24px; border-top: 1px solid #2a2d3a; color: var(--muted); font-size: 0.85rem; }
code { background: #1a1d28; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }
</style>
</head>
<body>
<div class=\"container\">
<h1>Privacy Policy</h1>
<p class=\"updated\">Last updated: September 15, 2026</p>
<h2>Overview</h2>
<p>Notability AI Bridge connects your Notability note backups from Google Drive to AI assistants via MCP. This Privacy Policy explains what data we collect and your rights.</p>
<h2>What We Collect</h2>
<ul>
<li><strong>Email:</strong> From Google OAuth. Used to identify your account.</li>
<li><strong>OAuth tokens:</strong> Google Drive access/refresh tokens. Stored in our database.</li>
<li><strong>Usage data:</strong> Tool call counts and timestamps. No note content is logged.</li>
</ul>
<h2>What We Do NOT Collect</h2>
<ul>
<li><strong>Note content is never stored.</strong> PDFs are streamed in real-time in memory and immediately discarded. Zero retention by design.</li>
<li><strong>We do not train AI models on your notes.</strong> We are a passthrough service.</li>
<li><strong>We do not sell or share your data.</strong></li>
</ul>
<h2>Google Drive Access</h2>
<p>We request <code>drive.readonly</code> scope - read-only access. We only access your \"Notability\" backup folder.</p>
<h2>Google API Limited Use Disclosure</h2>
<p>Our use of Google API services complies with the <a href=\"https://developers.google.com/terms/api-services-user-data-policy\">Google API Services User Data Policy</a>, including Limited Use requirements. We do not use Google API data for advertising, do not transfer it to third parties except as necessary for the service, and do not use it to train AI models.</p>
<h2>Data Retention</h2>
<ul>
<li><strong>Account data:</strong> Until account deletion.</li>
<li><strong>OAuth tokens:</strong> Until disconnect or account deletion.</li>
<li><strong>Usage logs:</strong> 90 days then auto-deleted.</li>
<li><strong>Note content:</strong> Never retained.</li>
</ul>
<h2>Your Rights</h2>
<ul>
<li><strong>Revoke access:</strong> <a href=\"https://myaccount.google.com/permissions\">Google Account Permissions</a></li>
<li><strong>Delete account:</strong> Email support@notabilitybridge.com</li>
<li><strong>GDPR/CCPA:</strong> Access, rectify, erase, restrict, port. Contact us to exercise.</li>
</ul>
<h2>Security</h2>
<ul>
<li>HTTPS/TLS encryption for all communication.</li>
<li>Cryptographically secure API key generation.</li>
<li>No passwords (Google OAuth only).</li>
</ul>
<h2>Contact</h2>
<p>Questions? Email <a href=\"mailto:support@notabilitybridge.com\">support@notabilitybridge.com</a></p>
<div class=\"footer\"><p>Notability AI Bridge is not affiliated with Notability (Ginger Labs) or Google.</p></div>
</div>
</body>
</html>\"\"\"

TERMS_HTML = \"\"\"<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Terms of Service - Notability AI Bridge</title>
<style>
:root { --bg: #0f1117; --text: #e4e4e7; --muted: #71717a; --accent: #6366f1; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }
.container { max-width: 720px; margin: 0 auto; padding: 60px 24px; }
h1 { font-size: 2rem; margin-bottom: 8px; }
.updated { color: var(--muted); font-size: 0.9rem; margin-bottom: 40px; }
h2 { font-size: 1.3rem; margin-top: 36px; margin-bottom: 12px; color: #a5b4fc; }
p { margin-bottom: 16px; }
ul { margin-bottom: 16px; padding-left: 24px; }
li { margin-bottom: 8px; }
a { color: var(--accent); }
.footer { margin-top: 60px; padding-top: 24px; border-top: 1px solid #2a2d3a; color: var(--muted); font-size: 0.85rem; }
</style>
</head>
<body>
<div class=\"container\">
<h1>Terms of Service</h1>
<p class=\"updated\">Last updated: September 15, 2026</p>
<h2>1. Acceptance</h2>
<p>By using Notability AI Bridge, you agree to these Terms.</p>
<h2>2. Service Description</h2>
<p>A passthrough service connecting Notability PDF backups in Google Drive to AI assistants via MCP.</p>
<h2>3. AI Processing Disclaimer</h2>
<p>Your note content is delivered to third-party AI assistants you connect. We do not control how they process your data. Review their privacy policies. We are not responsible for third-party AI handling.</p>
<h2>4. Plans</h2>
<ul>
<li><strong>Free:</strong> 50 calls/day. No warranty.</li>
<li><strong>Pro ($5/mo):</strong> 1,000 calls/day. Cancel anytime.</li>
<li><strong>Team ($15/mo):</strong> 5,000 calls/day.</li>
</ul>
<h2>5. Cancellation</h2>
<p>Cancel anytime via Stripe Customer Portal. No refunds for partial periods.</p>
<h2>6. Service Availability</h2>
<p>Provided \"as is\" without uptime guarantees. May be modified or discontinued.</p>
<h2>7. Limitation of Liability</h2>
<ul>
<li>Service provided \"AS IS\" without warranties.</li>
<li>Not liable for indirect, consequential, or punitive damages.</li>
<li>Total liability limited to amount paid in preceding 12 months.</li>
<li>Not liable for third-party AI processing.</li>
</ul>
<h2>8. Third-Party Services</h2>
<p>Relies on Google Drive, Railway, Stripe, and AI assistants. You must comply with their terms.</p>
<h2>9. Governing Law</h2>
<p>Laws of the State of New Jersey, USA.</p>
<h2>10. Contact</h2>
<p>Email <a href=\"mailto:support@notabilitybridge.com\">support@notabilitybridge.com</a></p>
<div class=\"footer\"><p>Notability AI Bridge is not affiliated with Notability (Ginger Labs) or Google.</p></div>
</div>
</body>
</html>\"\"\"
