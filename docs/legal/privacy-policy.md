# Privacy Policy — VeloraAi (DRAFT)

> **DRAFT — NOT LEGALLY REVIEWED.** Engineering starting point describing the
> system's actual data handling. Must be reviewed by Indonesian counsel and
> published in Bahasa Indonesia before launch. Governing law: UU PDP No. 27/2022.

Last updated: <DATE>

## 1. Controller

`<PT LEGAL NAME>`, `<ADDRESS>`. Privacy contact: `<EMAIL>`.
Data Protection Officer: `<NAME OR "not appointed; see §10">`.

## 2. What we collect

| Category | Examples | Why | Basis |
| --- | --- | --- | --- |
| Account | email, password hash (Argon2id), verification status | operate your account | contract |
| Usage | conversations, messages, uploaded documents, embeddings | deliver the service | contract |
| Billing | order IDs, amounts, payment status, invoice numbers | process payment, meet tax law | contract, legal obligation |
| Integrations | encrypted third-party tokens | run tools you request | consent |
| Technical | request IDs, timestamps, salted IP and email digests, user agent | security, abuse prevention, debugging | legitimate interest |
| Audit | security-relevant events with a user reference | accountability, incident response | legal obligation |

We do **not** collect payment card details. Midtrans handles card data; we never
see or store it.

## 3. How we use it

To provide and secure the service, process payments and issue invoices, prevent
abuse, comply with law, and — only with separate opt-in — send product updates.

**We do not sell personal data. We do not use your content to train AI models.**

## 4. Sharing

| Recipient | Purpose | Location |
| --- | --- | --- |
| `<AI PROVIDER>` | model inference on your prompts | `<COUNTRY>` |
| Midtrans | payment processing | Indonesia |
| `<HOSTING>` | application and database hosting | `<COUNTRY>` |
| `<ERROR TRACKING>` | crash diagnostics (no message content) | `<COUNTRY>` |
| Providers you connect | actions you or the assistant initiate | varies |

Transfers outside Indonesia rely on `<MECHANISM>`. `[counsel]`

## 5. Security

Passwords are hashed with Argon2id. Third-party credentials are encrypted with
AES-256-GCM, bound to your account so a ciphertext cannot be reused on another
account. Sessions are revocable and rotate on refresh. All traffic uses TLS.
Access to production data is restricted and audited. Untrusted code executes
only in an isolated, network-disabled sandbox.

No system is perfectly secure. Report concerns to `<SECURITY EMAIL>`.

## 6. Retention

| Data | Retention |
| --- | --- |
| Account | life of the account |
| Conversations and documents | until you delete them, or 30 days after closure |
| Billing records | 10 years (Indonesian tax law) |
| Audit logs | 2 years |
| Login attempts | 90 days |
| Encrypted credentials | until you disconnect or close the account |

Closing your account tombstones it and releases your email; billing and audit
records are retained as legally required.

## 7. Your rights under UU PDP

Access, rectification, erasure, restriction, objection, portability, and
withdrawal of consent. Exercise them at `<EMAIL>`; we respond within 30 days.

Currently self-service: deletion (`DELETE /api/v1/auth/me`), disconnecting
integrations, deleting individual conversations and documents.
Currently by request: full data export. `<Build the export endpoint.>`

## 8. Cookies

We use a session token stored in your browser to keep you signed in. No
advertising or third-party tracking cookies. `<Confirm before launch.>`

## 9. Children

VeloraAi is not for anyone under 18. We do not knowingly collect children's
data; contact us and we will delete it.

## 10. Breach notification

If a breach is likely to harm you, we notify you and the Indonesian authority
within **3×24 hours**, as UU PDP requires.

## 11. Changes

Material changes announced at least 30 days in advance by email and in-app.

## 12. Complaints

Contact `<EMAIL>` first. You may also complain to the Indonesian personal data
protection authority.
