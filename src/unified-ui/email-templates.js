/**
 * Modern Email Templates for Sales Proposals Platform
 *
 * These templates follow modern email design principles:
 * - Mobile-responsive design
 * - Clean, professional aesthetics
 * - Clear call-to-action buttons
 * - Accessible color contrast
 * - Inline CSS for email client compatibility
 */

const APP_NAME = process.env.APP_NAME || 'Sales Proposals';
const APP_URL = process.env.APP_URL || 'http://localhost:3005';
const COMPANY_NAME = process.env.COMPANY_NAME || 'Your Company';
const SUPPORT_EMAIL = process.env.SUPPORT_EMAIL || 'support@example.com';

// Brand colors
const COLORS = {
  primary: '#2563eb',      // Blue-600
  primaryDark: '#1d4ed8',  // Blue-700
  secondary: '#64748b',    // Slate-500
  background: '#f8fafc',   // Slate-50
  white: '#ffffff',
  text: '#1e293b',         // Slate-800
  textLight: '#64748b',    // Slate-500
  border: '#e2e8f0',       // Slate-200
  success: '#10b981',      // Emerald-500
  warning: '#f59e0b',      // Amber-500
};

/**
 * Base email layout wrapper
 */
function baseLayout(content, preheader = '') {
  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>${APP_NAME}</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
  <style>
    /* Reset styles */
    body, table, td, a { -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
    table, td { mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
    img { -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }
    body { height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; }
    a[x-apple-data-detectors] { color: inherit !important; text-decoration: none !important; font-size: inherit !important; font-family: inherit !important; font-weight: inherit !important; line-height: inherit !important; }

    /* Button hover effect */
    @media screen and (max-width: 600px) {
      .mobile-padding { padding: 20px !important; }
      .mobile-stack { display: block !important; width: 100% !important; }
    }
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: ${COLORS.background}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
  <!-- Preheader text (hidden preview text) -->
  <div style="display: none; max-height: 0; overflow: hidden; font-size: 1px; line-height: 1px; color: ${COLORS.background};">
    ${preheader}
    ${'&nbsp;'.repeat(100)}
  </div>

  <!-- Email wrapper -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: ${COLORS.background};">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <!-- Email container -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px; background-color: ${COLORS.white}; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
          ${content}
        </table>

        <!-- Footer -->
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px;">
          <tr>
            <td style="padding: 30px 40px; text-align: center;">
              <p style="margin: 0 0 10px; color: ${COLORS.textLight}; font-size: 13px; line-height: 1.5;">
                This email was sent by ${APP_NAME}
              </p>
              <p style="margin: 0; color: ${COLORS.textLight}; font-size: 13px; line-height: 1.5;">
                ${COMPANY_NAME} &bull; <a href="mailto:${SUPPORT_EMAIL}" style="color: ${COLORS.primary}; text-decoration: none;">${SUPPORT_EMAIL}</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
`;
}

/**
 * Primary action button component
 */
function primaryButton(text, url) {
  return `
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
  <tr>
    <td align="center" style="padding: 30px 0;">
      <!--[if mso]>
      <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="${url}" style="height:50px;v-text-anchor:middle;width:280px;" arcsize="10%" stroke="f" fillcolor="${COLORS.primary}">
        <w:anchorlock/>
        <center style="color:#ffffff;font-family:sans-serif;font-size:16px;font-weight:bold;">
          ${text}
        </center>
      </v:roundrect>
      <![endif]-->
      <!--[if !mso]><!-->
      <a href="${url}" target="_blank" style="display: inline-block; padding: 16px 48px; background-color: ${COLORS.primary}; color: ${COLORS.white}; text-decoration: none; font-size: 16px; font-weight: 600; border-radius: 8px; transition: background-color 0.2s;">
        ${text}
      </a>
      <!--<![endif]-->
    </td>
  </tr>
</table>
`;
}

/**
 * Secondary/outline button component
 */
function secondaryButton(text, url) {
  return `
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
  <tr>
    <td align="center" style="padding: 15px 0;">
      <a href="${url}" target="_blank" style="display: inline-block; padding: 12px 32px; background-color: transparent; color: ${COLORS.primary}; text-decoration: none; font-size: 14px; font-weight: 600; border: 2px solid ${COLORS.primary}; border-radius: 8px;">
        ${text}
      </a>
    </td>
  </tr>
</table>
`;
}

/**
 * Info box component
 */
function infoBox(content, type = 'info') {
  const bgColor = type === 'warning' ? '#fef3c7' : '#eff6ff';
  const borderColor = type === 'warning' ? COLORS.warning : COLORS.primary;

  return `
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
  <tr>
    <td style="padding: 20px; background-color: ${bgColor}; border-left: 4px solid ${borderColor}; border-radius: 0 8px 8px 0;">
      <p style="margin: 0; color: ${COLORS.text}; font-size: 14px; line-height: 1.6;">
        ${content}
      </p>
    </td>
  </tr>
</table>
`;
}

/**
 * Token display component (for displaying invite tokens)
 */
function tokenDisplay(token) {
  return `
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
  <tr>
    <td style="padding: 20px; background-color: ${COLORS.background}; border-radius: 8px; text-align: center;">
      <p style="margin: 0 0 8px; color: ${COLORS.textLight}; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">
        Your Invite Token
      </p>
      <p style="margin: 0; color: ${COLORS.text}; font-size: 18px; font-family: 'Courier New', Courier, monospace; font-weight: 600; word-break: break-all;">
        ${token}
      </p>
    </td>
  </tr>
</table>
`;
}

// =============================================================================
// EMAIL TEMPLATES
// =============================================================================

/**
 * Invite Email Template
 * Sent when an admin invites a new user to join the platform
 */
function inviteEmail({ recipientEmail, recipientName, inviterName, inviterEmail, token, profileName, expiresAt, signupUrl }) {
  const preheader = `You've been invited to join ${APP_NAME}! Accept your invitation to get started.`;
  const displayName = recipientName || recipientEmail.split('@')[0];
  const profileDisplay = formatProfileName(profileName);
  const expiryDate = formatDate(expiresAt);

  // Build signup URL with token
  const fullSignupUrl = `${signupUrl || APP_URL + '/signup'}?token=${encodeURIComponent(token)}&email=${encodeURIComponent(recipientEmail)}`;

  const content = `
    <!-- Header with logo placeholder -->
    <tr>
      <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid ${COLORS.border};">
        <div style="width: 60px; height: 60px; background: linear-gradient(135deg, ${COLORS.primary} 0%, ${COLORS.primaryDark} 100%); border-radius: 12px; display: inline-block; line-height: 60px; margin-bottom: 20px;">
          <span style="color: white; font-size: 24px; font-weight: bold;">SP</span>
        </div>
        <h1 style="margin: 0; color: ${COLORS.text}; font-size: 24px; font-weight: 700; line-height: 1.3;">
          You're Invited!
        </h1>
      </td>
    </tr>

    <!-- Main content -->
    <tr>
      <td class="mobile-padding" style="padding: 40px;">
        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          Hi ${escapeHtml(displayName)},
        </p>

        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          <strong>${escapeHtml(inviterName || inviterEmail)}</strong> has invited you to join <strong>${APP_NAME}</strong> as a <strong>${profileDisplay}</strong>.
        </p>

        <p style="margin: 0 0 30px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          Click the button below to create your account and get started.
        </p>

        ${primaryButton('Accept Invitation', fullSignupUrl)}

        <div style="margin: 30px 0; padding: 0;">
          ${infoBox(`This invitation expires on <strong>${expiryDate}</strong>. If you don't recognize the sender or weren't expecting this invitation, you can safely ignore this email.`)}
        </div>

        <p style="margin: 0 0 15px; color: ${COLORS.textLight}; font-size: 14px; line-height: 1.6;">
          If the button doesn't work, copy and paste this link into your browser:
        </p>
        <p style="margin: 0; color: ${COLORS.primary}; font-size: 13px; line-height: 1.6; word-break: break-all;">
          <a href="${fullSignupUrl}" style="color: ${COLORS.primary}; text-decoration: underline;">
            ${fullSignupUrl}
          </a>
        </p>
      </td>
    </tr>

    <!-- What to expect section -->
    <tr>
      <td style="padding: 0 40px 40px;">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: ${COLORS.background}; border-radius: 12px;">
          <tr>
            <td style="padding: 25px;">
              <h3 style="margin: 0 0 15px; color: ${COLORS.text}; font-size: 16px; font-weight: 600;">
                What you'll get access to:
              </h3>
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td style="padding: 8px 0;">
                    <span style="color: ${COLORS.success}; font-size: 16px; margin-right: 10px;">&#10003;</span>
                    <span style="color: ${COLORS.text}; font-size: 14px;">Create and manage sales proposals</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 8px 0;">
                    <span style="color: ${COLORS.success}; font-size: 16px; margin-right: 10px;">&#10003;</span>
                    <span style="color: ${COLORS.text}; font-size: 14px;">Generate product mockups with AI</span>
                  </td>
                </tr>
                <tr>
                  <td style="padding: 8px 0;">
                    <span style="color: ${COLORS.success}; font-size: 16px; margin-right: 10px;">&#10003;</span>
                    <span style="color: ${COLORS.text}; font-size: 14px;">Collaborate with your team</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  `;

  return baseLayout(content, preheader);
}

/**
 * Welcome Email Template
 * Sent after a user successfully creates their account
 */
function welcomeEmail({ recipientEmail, recipientName, loginUrl }) {
  const preheader = `Welcome to ${APP_NAME}! Your account is ready.`;
  const displayName = recipientName || recipientEmail.split('@')[0];

  const content = `
    <!-- Header -->
    <tr>
      <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid ${COLORS.border};">
        <div style="width: 60px; height: 60px; background: linear-gradient(135deg, ${COLORS.success} 0%, #059669 100%); border-radius: 12px; display: inline-block; line-height: 60px; margin-bottom: 20px;">
          <span style="color: white; font-size: 28px;">&#10003;</span>
        </div>
        <h1 style="margin: 0; color: ${COLORS.text}; font-size: 24px; font-weight: 700; line-height: 1.3;">
          Welcome to ${APP_NAME}!
        </h1>
      </td>
    </tr>

    <!-- Main content -->
    <tr>
      <td class="mobile-padding" style="padding: 40px;">
        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          Hi ${escapeHtml(displayName)},
        </p>

        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          Your account has been created successfully. You're all set to start using ${APP_NAME}.
        </p>

        ${primaryButton('Go to Dashboard', loginUrl || APP_URL)}

        <h3 style="margin: 40px 0 20px; color: ${COLORS.text}; font-size: 18px; font-weight: 600;">
          Getting Started
        </h3>

        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
          <tr>
            <td style="padding: 15px 0; border-bottom: 1px solid ${COLORS.border};">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td width="40" valign="top">
                    <div style="width: 32px; height: 32px; background-color: ${COLORS.primary}; border-radius: 50%; text-align: center; line-height: 32px; color: white; font-weight: bold;">1</div>
                  </td>
                  <td style="padding-left: 15px;">
                    <p style="margin: 0 0 5px; color: ${COLORS.text}; font-size: 15px; font-weight: 600;">Create your first proposal</p>
                    <p style="margin: 0; color: ${COLORS.textLight}; font-size: 14px;">Use our AI-powered tools to generate professional sales proposals in minutes.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 15px 0; border-bottom: 1px solid ${COLORS.border};">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td width="40" valign="top">
                    <div style="width: 32px; height: 32px; background-color: ${COLORS.primary}; border-radius: 50%; text-align: center; line-height: 32px; color: white; font-weight: bold;">2</div>
                  </td>
                  <td style="padding-left: 15px;">
                    <p style="margin: 0 0 5px; color: ${COLORS.text}; font-size: 15px; font-weight: 600;">Generate mockups</p>
                    <p style="margin: 0; color: ${COLORS.textLight}; font-size: 14px;">Visualize products with AI-generated mockups on various backgrounds.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 15px 0;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                  <td width="40" valign="top">
                    <div style="width: 32px; height: 32px; background-color: ${COLORS.primary}; border-radius: 50%; text-align: center; line-height: 32px; color: white; font-weight: bold;">3</div>
                  </td>
                  <td style="padding-left: 15px;">
                    <p style="margin: 0 0 5px; color: ${COLORS.text}; font-size: 15px; font-weight: 600;">Track your bookings</p>
                    <p style="margin: 0; color: ${COLORS.textLight}; font-size: 14px;">Manage booking orders and track progress through your pipeline.</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Help section -->
    <tr>
      <td style="padding: 0 40px 40px;">
        <div style="padding: 20px; background-color: ${COLORS.background}; border-radius: 12px; text-align: center;">
          <p style="margin: 0 0 10px; color: ${COLORS.text}; font-size: 14px;">
            Need help getting started?
          </p>
          <p style="margin: 0; color: ${COLORS.textLight}; font-size: 14px;">
            Contact us at <a href="mailto:${SUPPORT_EMAIL}" style="color: ${COLORS.primary}; text-decoration: none;">${SUPPORT_EMAIL}</a>
          </p>
        </div>
      </td>
    </tr>
  `;

  return baseLayout(content, preheader);
}

/**
 * Password Reset Email Template
 */
function passwordResetEmail({ recipientEmail, recipientName, resetUrl, expiresInMinutes = 60 }) {
  const preheader = `Reset your ${APP_NAME} password. This link expires in ${expiresInMinutes} minutes.`;
  const displayName = recipientName || recipientEmail.split('@')[0];

  const content = `
    <!-- Header -->
    <tr>
      <td style="padding: 40px 40px 20px; text-align: center; border-bottom: 1px solid ${COLORS.border};">
        <div style="width: 60px; height: 60px; background: linear-gradient(135deg, ${COLORS.warning} 0%, #d97706 100%); border-radius: 12px; display: inline-block; line-height: 60px; margin-bottom: 20px;">
          <span style="color: white; font-size: 28px;">&#128274;</span>
        </div>
        <h1 style="margin: 0; color: ${COLORS.text}; font-size: 24px; font-weight: 700; line-height: 1.3;">
          Reset Your Password
        </h1>
      </td>
    </tr>

    <!-- Main content -->
    <tr>
      <td class="mobile-padding" style="padding: 40px;">
        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          Hi ${escapeHtml(displayName)},
        </p>

        <p style="margin: 0 0 20px; color: ${COLORS.text}; font-size: 16px; line-height: 1.6;">
          We received a request to reset the password for your ${APP_NAME} account. Click the button below to create a new password.
        </p>

        ${primaryButton('Reset Password', resetUrl)}

        <div style="margin: 30px 0;">
          ${infoBox(`This link will expire in <strong>${expiresInMinutes} minutes</strong>. If you didn't request a password reset, you can safely ignore this email.`, 'warning')}
        </div>

        <p style="margin: 0 0 15px; color: ${COLORS.textLight}; font-size: 14px; line-height: 1.6;">
          If the button doesn't work, copy and paste this link into your browser:
        </p>
        <p style="margin: 0; color: ${COLORS.primary}; font-size: 13px; line-height: 1.6; word-break: break-all;">
          <a href="${resetUrl}" style="color: ${COLORS.primary}; text-decoration: underline;">
            ${resetUrl}
          </a>
        </p>
      </td>
    </tr>
  `;

  return baseLayout(content, preheader);
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function escapeHtml(text) {
  if (!text) return '';
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

function formatProfileName(profileName) {
  if (!profileName) return 'Team Member';
  return profileName
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatDate(dateString) {
  if (!dateString) return 'soon';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

// =============================================================================
// EXPORTS
// =============================================================================

module.exports = {
  inviteEmail,
  welcomeEmail,
  passwordResetEmail,
  baseLayout,
  primaryButton,
  secondaryButton,
  infoBox,
  tokenDisplay,
  COLORS,
  APP_NAME,
  APP_URL,
  COMPANY_NAME,
  SUPPORT_EMAIL,
};
