# Legal and compliance checklist (Indonesia)

**This is an engineering checklist, not legal advice.** Every item marked
`[counsel]` must be reviewed by a qualified Indonesian lawyer or tax consultant
before you take money from the public.

---

## 1. Corporate entity

- [ ] Establish a legal entity — **PT** (or **PT PMA** if there is foreign
      ownership). Operating a paid consumer service as an individual exposes
      your personal assets to unlimited liability. `[counsel]`
- [ ] Obtain **NIB** (Nomor Induk Berusaha) via OSS.
- [ ] Register the correct **KBLI** codes — typically 62019 (computer
      programming) and 63122 (web portals). `[counsel]`
- [ ] Obtain company **NPWP**.
- [ ] Open a corporate bank account. Midtrans settlement must not land in a
      personal account.
- [ ] Register the **VeloraAi** trademark with DJKI before public launch.

## 2. Tax

- [ ] Register as **PKP** (taxable entrepreneur) once turnover exceeds the
      threshold; registration is mandatory beyond it. `[counsel]`
- [ ] **PPN at 12%** applies to digital services sold to Indonesian customers.
      Decide tax-inclusive vs tax-exclusive pricing and set `VAT_PERCENT`
      accordingly. The codebase treats configured prices as **tax inclusive**
      and stores the extracted tax in `payments.tax_amount`. `[counsel]`
- [ ] Issue compliant **Faktur Pajak** for PKP customers. `payments.invoice_number`
      provides the sequential reference; e-Faktur integration is still required.
- [ ] Withholding tax (PPh 23 / PPh 26) on payments to foreign suppliers such
      as OpenAI. `[counsel]`
- [ ] Monthly and annual filings — assign an owner.

## 3. Personal data — UU PDP No. 27/2022

VeloraAi processes email addresses, chat content, uploaded documents, payment
records, and encrypted third-party credentials. All are personal data.

- [ ] Publish a **Privacy Policy** in Bahasa Indonesia (`privacy-policy.md` is
      an English starting point only). `[counsel]`
- [ ] Record a lawful basis for each processing purpose.
- [ ] Obtain explicit, unbundled consent where consent is the basis.
- [ ] Implement data-subject rights. Current status:
  - [x] Right to erasure — `DELETE /api/v1/auth/me` (soft delete, financial
        records retained as legally required)
  - [ ] Right of access / portability — **export endpoint not yet built**
  - [ ] Right to rectification — partially covered by account settings
- [ ] Appoint a **Data Protection Officer** if required by scale. `[counsel]`
- [ ] Breach notification within **3×24 hours** to the authority and to affected
      subjects. Procedure is in `docs/runbook.md` §9.
- [ ] Document a data-retention schedule and enforce it in the maintenance job.
- [ ] Assess cross-border transfers — OpenAI, Midtrans, Cloudflare, Vercel,
      and Railway all process data outside Indonesia. `[counsel]`
- [ ] Sign data-processing agreements with each processor.

## 4. Consumer protection — UU No. 8/1999

- [ ] Publish **Terms of Service** in Bahasa Indonesia. `[counsel]`
- [ ] State prices in IDR, inclusive of tax, before checkout.
- [ ] Publish a clear refund policy. Refunds are implemented
      (`POST /api/v1/payments/{id}/refund`, admin only) but the customer-facing
      policy is not written.
- [ ] Describe the cancellation flow. `cancel_at_period_end` preserves access
      through the paid period — say so explicitly.
- [ ] Provide a working support channel and a physical business address.
- [ ] Give advance notice of price changes.

## 5. Payments

- [ ] Complete Midtrans production onboarding (entity documents required).
- [ ] Never store card data. VeloraAi stores only order IDs, Snap tokens, and
      transaction references — keep it that way.
- [ ] Reconcile Midtrans settlement against `payments` at least monthly.
- [ ] Document the chargeback and dispute process.

## 6. AI-specific disclosures

- [ ] Disclose that responses are AI generated and may be inaccurate.
- [ ] Disclose that prompts are transmitted to third-party model providers.
- [ ] State whether user content is used for training (it is not; say so).
- [ ] Publish an acceptable-use policy prohibiting illegal and abusive use.
- [ ] Document that tool execution acts on the user's **own** connected
      credentials, and the scope of access each provider grants.

## 7. Employment, when you hire

- [ ] Written employment agreements compliant with UU Cipta Kerja. `[counsel]`
- [ ] IP assignment clauses so company code is owned by the company.
- [ ] BPJS Kesehatan and BPJS Ketenagakerjaan registration.
- [ ] Contractor agreements with explicit IP assignment (see `CONTRIBUTING.md`).

## 8. Insurance and governance

- [ ] Professional indemnity / cyber liability cover.
- [ ] Board minutes and a shareholder register from day one — acquirers and
      investors will ask for them in diligence.
- [ ] Keep an IP register: repositories, trademarks, domains, design assets.

---

## Launch gate

Do not accept payment from the public until, at minimum, items 1 (entity, NIB,
NPWP, bank account), 2 (PKP and PPN handling), 3 (Privacy Policy, data-subject
rights, breach procedure), 4 (ToS, refund policy, support channel), and 5
(Midtrans production onboarding) are complete.
