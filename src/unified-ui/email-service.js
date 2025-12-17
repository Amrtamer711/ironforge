/**
 * Email Service for Sales Proposals Platform
 *
 * Supports multiple email providers:
 * - Resend (recommended)
 * - SendGrid
 * - SMTP (generic)
 * - Console (development only - logs to console)
 *
 * Configuration via environment variables:
 * - EMAIL_PROVIDER: 'resend', 'sendgrid', 'smtp', or 'console'
 * - EMAIL_FROM: Default from address
 * - RESEND_API_KEY: API key for Resend
 * - SENDGRID_API_KEY: API key for SendGrid
 * - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS: SMTP configuration
 */

const emailTemplates = require('./email-templates');

// =============================================================================
// CONFIGURATION
// =============================================================================

const EMAIL_PROVIDER = process.env.EMAIL_PROVIDER || 'console';
const EMAIL_FROM = process.env.EMAIL_FROM || `${emailTemplates.APP_NAME} <noreply@example.com>`;

// Provider-specific config
const RESEND_API_KEY = process.env.RESEND_API_KEY;
const SENDGRID_API_KEY = process.env.SENDGRID_API_KEY;
const SMTP_CONFIG = {
  host: process.env.SMTP_HOST,
  port: parseInt(process.env.SMTP_PORT || '587', 10),
  secure: process.env.SMTP_SECURE === 'true',
  user: process.env.SMTP_USER,
  pass: process.env.SMTP_PASS,
};

// =============================================================================
// EMAIL PROVIDERS
// =============================================================================

/**
 * Console provider - logs emails to console (for development)
 */
async function sendViaConsole({ to, subject, html }) {
  console.log('\n' + '='.repeat(60));
  console.log('EMAIL (Console Provider - Development Mode)');
  console.log('='.repeat(60));
  console.log(`To: ${to}`);
  console.log(`From: ${EMAIL_FROM}`);
  console.log(`Subject: ${subject}`);
  console.log('-'.repeat(60));
  console.log('HTML content length:', html.length, 'characters');
  console.log('='.repeat(60) + '\n');

  return { success: true, messageId: `console-${Date.now()}` };
}

/**
 * Resend provider - using fetch API
 * https://resend.com/docs/api-reference/emails/send-email
 */
async function sendViaResend({ to, subject, html }) {
  if (!RESEND_API_KEY) {
    throw new Error('RESEND_API_KEY is not configured');
  }

  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${RESEND_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: EMAIL_FROM,
      to: Array.isArray(to) ? to : [to],
      subject,
      html,
    }),
  });

  const data = await response.json();

  if (!response.ok) {
    console.error('[Email] Resend error:', data);
    throw new Error(data.message || 'Failed to send email via Resend');
  }

  console.log(`[Email] Sent via Resend: ${data.id}`);
  return { success: true, messageId: data.id };
}

/**
 * SendGrid provider - using fetch API
 * https://docs.sendgrid.com/api-reference/mail-send/mail-send
 */
async function sendViaSendGrid({ to, subject, html }) {
  if (!SENDGRID_API_KEY) {
    throw new Error('SENDGRID_API_KEY is not configured');
  }

  const response = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${SENDGRID_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: to }] }],
      from: { email: EMAIL_FROM.match(/<(.+)>/)?.[1] || EMAIL_FROM },
      subject,
      content: [{ type: 'text/html', value: html }],
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    console.error('[Email] SendGrid error:', text);
    throw new Error(`Failed to send email via SendGrid: ${response.status}`);
  }

  const messageId = response.headers.get('x-message-id') || `sendgrid-${Date.now()}`;
  console.log(`[Email] Sent via SendGrid: ${messageId}`);
  return { success: true, messageId };
}

/**
 * SMTP provider - using nodemailer (if available)
 */
async function sendViaSMTP({ to, subject, html }) {
  // Dynamically require nodemailer (optional dependency)
  let nodemailer;
  try {
    nodemailer = require('nodemailer');
  } catch (err) {
    throw new Error('nodemailer is not installed. Run: npm install nodemailer');
  }

  if (!SMTP_CONFIG.host || !SMTP_CONFIG.user || !SMTP_CONFIG.pass) {
    throw new Error('SMTP configuration incomplete. Set SMTP_HOST, SMTP_USER, and SMTP_PASS');
  }

  const transporter = nodemailer.createTransport({
    host: SMTP_CONFIG.host,
    port: SMTP_CONFIG.port,
    secure: SMTP_CONFIG.secure,
    auth: {
      user: SMTP_CONFIG.user,
      pass: SMTP_CONFIG.pass,
    },
  });

  const result = await transporter.sendMail({
    from: EMAIL_FROM,
    to,
    subject,
    html,
  });

  console.log(`[Email] Sent via SMTP: ${result.messageId}`);
  return { success: true, messageId: result.messageId };
}

// =============================================================================
// MAIN EMAIL FUNCTION
// =============================================================================

/**
 * Send an email using the configured provider
 *
 * @param {Object} options
 * @param {string} options.to - Recipient email address
 * @param {string} options.subject - Email subject
 * @param {string} options.html - HTML content
 * @returns {Promise<{success: boolean, messageId: string}>}
 */
async function sendEmail({ to, subject, html }) {
  console.log(`[Email] Sending to ${to} via ${EMAIL_PROVIDER}: "${subject}"`);

  try {
    switch (EMAIL_PROVIDER.toLowerCase()) {
      case 'resend':
        return await sendViaResend({ to, subject, html });

      case 'sendgrid':
        return await sendViaSendGrid({ to, subject, html });

      case 'smtp':
        return await sendViaSMTP({ to, subject, html });

      case 'console':
      default:
        return await sendViaConsole({ to, subject, html });
    }
  } catch (err) {
    console.error(`[Email] Failed to send to ${to}:`, err.message);
    throw err;
  }
}

// =============================================================================
// HIGH-LEVEL EMAIL FUNCTIONS
// =============================================================================

/**
 * Send an invite email to a new user
 *
 * @param {Object} options
 * @param {string} options.recipientEmail - Email of the invited user
 * @param {string} [options.recipientName] - Name of the invited user
 * @param {string} options.inviterName - Name of the person sending the invite
 * @param {string} options.inviterEmail - Email of the person sending the invite
 * @param {string} options.token - The invite token
 * @param {string} options.profileName - The profile being assigned
 * @param {string} options.expiresAt - ISO date string of when the invite expires
 * @param {string} [options.signupUrl] - Custom signup URL
 */
async function sendInviteEmail(options) {
  const html = emailTemplates.inviteEmail(options);

  return sendEmail({
    to: options.recipientEmail,
    subject: `You're invited to join ${emailTemplates.APP_NAME}`,
    html,
  });
}

/**
 * Send a welcome email to a new user after signup
 *
 * @param {Object} options
 * @param {string} options.recipientEmail - Email of the new user
 * @param {string} [options.recipientName] - Name of the new user
 * @param {string} [options.loginUrl] - URL to the login page
 */
async function sendWelcomeEmail(options) {
  const html = emailTemplates.welcomeEmail(options);

  return sendEmail({
    to: options.recipientEmail,
    subject: `Welcome to ${emailTemplates.APP_NAME}!`,
    html,
  });
}

/**
 * Send a password reset email
 *
 * @param {Object} options
 * @param {string} options.recipientEmail - Email of the user
 * @param {string} [options.recipientName] - Name of the user
 * @param {string} options.resetUrl - URL to reset password
 * @param {number} [options.expiresInMinutes=60] - Minutes until link expires
 */
async function sendPasswordResetEmail(options) {
  const html = emailTemplates.passwordResetEmail(options);

  return sendEmail({
    to: options.recipientEmail,
    subject: `Reset your ${emailTemplates.APP_NAME} password`,
    html,
  });
}

// =============================================================================
// EXPORTS
// =============================================================================

module.exports = {
  sendEmail,
  sendInviteEmail,
  sendWelcomeEmail,
  sendPasswordResetEmail,
  EMAIL_PROVIDER,
  EMAIL_FROM,
};
