# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of Script Manager seriously. If you believe you have found a security vulnerability, please report it to us as described below.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them using one of the following methods:

1. **GitHub Security Advisories** (Preferred)
   - Go to the [Security tab](https://github.com/jomardyan/Script-Manager/security) of this repository
   - Click "Report a vulnerability"
   - Fill out the form with details

2. **Email**
   - Send an email to the repository maintainer (contact information available on GitHub profile)
   - Include "SECURITY" in the subject line

### What to Include

Please include the following information in your report:

- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the vulnerability, including how an attacker might exploit it

### What to Expect

- You should receive an acknowledgment within 48 hours
- We will investigate and send you a more detailed response within 7 days
- We will work on a fix and coordinate the disclosure timeline with you
- We will credit you for the discovery (unless you prefer to remain anonymous)

## Security Best Practices

When deploying Script Manager in production:

### Critical Requirements

1. **Change the SECRET_KEY**
   ```bash
   # Generate a secure key
   openssl rand -hex 32
   ```
   Set this as the `SECRET_KEY` environment variable before deploying.

2. **Use HTTPS**
   - Always deploy behind a reverse proxy with SSL/TLS
   - Never expose the application over HTTP in production

3. **Restrict CORS Origins**
   - Set `ALLOWED_ORIGINS` to only your production domains
   - Never use `*` in production

4. **Secure Database**
   - Use strong passwords for MySQL/PostgreSQL
   - Restrict network access to database
   - Enable SSL/TLS for database connections

5. **Update Regularly**
   - Keep dependencies up to date
   - Monitor for security advisories
   - Apply security patches promptly

### Additional Recommendations

- Enable rate limiting at the reverse proxy level
- Use environment variables for all sensitive configuration
- Implement network segmentation
- Enable audit logging
- Regular security assessments
- Backup your database regularly
- Use container security scanning in CI/CD

For more detailed security guidance, see our [Production Deployment Guide](./docs/PRODUCTION.md).

## Known Security Considerations

### JWT Tokens

- Tokens are valid for 24 hours by default
- Tokens are signed with SECRET_KEY
- No token revocation mechanism is currently implemented
- For sensitive operations, implement additional authentication checks

### File Upload

- Attachments are stored on the server filesystem
- File type validation is based on extension
- Consider implementing antivirus scanning for production deployments
- Set appropriate file size limits

### Database

- SQLite is used by default (single-file, no network exposure)
- For production, consider PostgreSQL with proper access controls
- Database credentials are stored in environment variables

### Script Execution

- Scheduled jobs execute shell commands
- Jobs run with the permissions of the backend process
- Implement proper access controls and auditing
- Consider running jobs in isolated containers

## Security Updates

We will announce security updates through:

1. GitHub Security Advisories
2. Release notes
3. This SECURITY.md file

## Compliance

Script Manager is designed to be deployed in various environments. Depending on your use case, you may need to implement additional controls for:

- GDPR (General Data Protection Regulation)
- HIPAA (Health Insurance Portability and Accountability Act)
- SOC 2 (Service Organization Control 2)
- PCI DSS (Payment Card Industry Data Security Standard)

Please review our [Production Deployment Guide](./docs/PRODUCTION.md) for guidance on security controls.

## Vulnerability Disclosure Policy

When we receive a security vulnerability report:

1. We will confirm receipt within 48 hours
2. We will assess the severity and impact
3. We will develop and test a fix
4. We will prepare a security advisory
5. We will coordinate disclosure with the reporter
6. We will release the fix and advisory simultaneously
7. We will credit the reporter (unless anonymous)

## Attribution

We thank the security researchers who have responsibly disclosed vulnerabilities to us.

---

**Last Updated:** April 2026
