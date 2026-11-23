# AGENTS.md

Notes for coding agents (Claude Code, Codex, Cursor) working in this repo.
People should start with [README.md](README.md).

Hawlak turns a hospital discharge PDF into an insurer-approved follow-up
journey. The journey has four parts:

- one WhatsApp voice note in the patient's Saudi dialect
- a reminder for each medicine
- scheduled follow-up calls
- a limited caregiver view

The hospital uploads the PDF and the member ID. Hawlak drafts the content and
checks eligibility. The insurer reviews, edits, schedules and approves, and a
worker then delivers. The AI changes wording and dialect only.

The current state, what is done and what is planned are in
[README.md → Status](README.md#status-12-november-2026). Update that section
when you finish a milestone.

## Who owns what

| Path | Owner | Stack |
|---|---|---|
| `apps/api` | Haya | Python 3.12, FastAPI, SQLAlchemy, Alembic, uv |
| `apps/dashboard` | Retaj | React 19 + TypeScript, Vite |
| `apps/agent` | Haya | Python, LiveKit worker + control server (:3100) |
| `deploy/aws`, `docker-compose.aws.yml` | Haya | EC2 + Docker Compose, CloudFront, S3, SSM |
| `packages/contracts`, `docs/integration-contract.md` | both | Zod |
| `docs/design-system` | both | Tokens and screen references for UI work |

## Where things live

| Concern | File |
|---|---|
| Intake, approval and scheduling rules | `apps/api/app/services/care_journey_service.py` |
| PDF parsing | `apps/api/app/services/discharge_parser.py` |
| Drafting and the fidelity guard | `apps/api/app/services/journey_drafter.py` |
| Drafting prompt (versioned) | `apps/api/app/prompts/journey-draft-v5.txt` |
| Dose details with their source, tablet count, reminder times | `apps/api/app/services/dose_facts.py` |
| Patient-text identifier gate | `apps/api/app/services/patient_identifiers.py` |
| Medicine-photo label check and fixed replies | `apps/api/app/services/medicine_photos.py` |
| Inbound WhatsApp (patient or caregiver) and caregiver photo upload | `apps/api/app/services/inbound_workflow.py` |
| Programme analytics and worklist stage (aggregates only) | `apps/api/app/services/analytics.py` |
| Mock insurer eligibility and enrollment | `apps/api/app/services/insurer_systems.py` |
| Meta and call dispatch | `apps/api/app/services/journey_delivery.py` |
| Role APIs | `apps/api/app/routes/care_journeys.py` |
| Insurer, hospital and caregiver UI | `apps/dashboard/src/*Workspace.tsx` |
| Browser/API contract | `apps/dashboard/src/api.ts` |
| Data flow, privacy boundary, threat model | `docs/architecture/platform-data-privacy.md` |

Read the privacy doc before changing what data leaves Hawlak, and update its
status table when you change it.

Stay inside the app you were asked to change. Changes to the contract need a
pull request reviewed by both Haya and Retaj.

## Rules

- Synthetic patients and fictional medicines only. Never commit `.env`, real
  phone numbers, patient data or generated audio.
- Clinical content comes only from the approved plan. Nothing reaches a patient
  until its exact script is approved. The one exception is the follow-up call
  agent: code picks every step, and a chat model phrases it using only the
  approved call plan, voice note and reminder scripts. The speech guard
  (`apps/agent/src/hawlak_agent/speech_guard.py`) replaces any sentence that has a
  number outside that content or runs over 40 words with the approved question.
  Opening, completion and transfer scripts are spoken word for word, and the
  care-team transfer lines are fixed in `TRANSFER_LINES` (`transfer.py`), like
  `PHOTO_REPLIES`.
- The voice note carries discharge instructions only. Medicines go in their own
  reminders and the photo request, never in the voice note.
- Never log tokens or full phone numbers (last 4 digits only).
- Medicine photos come only from the patient or the registered caregiver, never
  the insurer. They arrive on WhatsApp, or the caregiver uploads one in the
  caregiver view for a medicine that still has no usable photo. Hawlak asks for each approved medicine by name, and each photo is
  linked to the medicine it was requested for (its slot), never by model guess.
  The vision model reads only the printed label; code compares it with that one
  medicine. The one exception is a box sent out of order: when the label fails
  the requested medicine and code matches it to exactly one other approved
  medicine still waiting for its photo, the photo is linked there instead. Senders get only the fixed replies in `PHOTO_REPLIES`, never a
  verdict; a mismatch becomes an alert for a person. Design:
  [`docs/architecture/medicine-photo-check.md`](docs/architecture/medicine-photo-check.md).
- Analytics returns counts, rates and times only: never a name, a phone number
  or a case reference.
- `apps/api` holds no UI code. `apps/dashboard` holds no AI, WhatsApp, database
  or storage code; it only calls the API.
- Generated drafts must pass `guard_draft`, which checks numbers, medicine names
  and doses. A draft that fails falls back to the template. Change the prompt by
  adding a new versioned file, not by editing the old one in place.
- Tablet or capsule counts and reminder times come only from the fixed fields in
  `dose_facts.py`, each with its source (`prescribed`, `calculated`,
  `reminder_preference`, `unknown`). Code calculates; the model only phrases. Never
  turn a frequency into a clock time or an interval, never offer part of a tablet,
  and never fill in an `unknown`.
- Patient-facing text never carries the registered full name, a phone number, a
  national or Iqama number, a member or policy number, the case ID or the
  source filename. `find_identifier` blocks approval when it finds one. Never
  fall back to `patientName` when no approved form of address exists.
- Mock delivery must look like mock delivery. Runs with a `mock:` provider
  reference show "Simulated — not actually sent". Never show them as sent.
- Do not hard-code provider values, phone numbers, patient data or scripts.
- Write the test first. Work is done when the checks below pass.
- Branches: `haya/<feature>` or `retaj/<feature>`. `main` stays demo-ready.
- Commit as the human author only, with no AI co-author or attribution lines.
  Push only when asked.

## Commands

From the repo root:

| Task | Command |
|---|---|
| Start Postgres and MinIO | `docker compose up -d postgres minio minio-init` |
| Run the API (port 3000) | `npm run dev:api` |
| Run the dashboard (port 5173) | `npm run dev -w apps/dashboard` |
| Node checks | `npm run typecheck && npm test && npm run build` |
| API tests | `uv run --directory apps/api pytest` |
| API lint | `uv run --directory apps/api ruff check . && uv run --directory apps/api ruff format --check .` |
| Keyless demo | `uv run --directory apps/api python -m scripts.demo --mock --case abu-mohammed` |
| Delivery worker | `npm run dev:worker` |
| DB migrations | `uv run --directory apps/api alembic upgrade head` (needs `DATABASE_URL` from `.env`) |
| AWS release | `deploy/aws/deploy.sh` |
| Provider keys to AWS | `deploy/aws/sync_keys.sh --check`, then `deploy/aws/sync_keys.sh` |

Tests use mocks; no provider keys are needed. Keep `DEMO_PROVIDER_MODE=mock`
locally.

The repo is synced by iCloud. Keep the Python venv outside it:
`export UV_PROJECT_ENVIRONMENT="$HOME/.cache/hawlak-api-venv"`. iCloud also
creates `* 2` duplicate files and folders. Never commit them. Delete them from
`node_modules` when a typecheck fails strangely.

## AWS demo

- The demo uses AWS profile `hawlak` in eu-north-1 only.
- There is no SSH. Use Session Manager.
- Secrets live in the SSM SecureString `/hawlak/demo/env`. Never print them.
- Never type the demo password or provider keys into the hosted site. People
  paste keys into their local `.env` themselves.
- The stack stays running unless Haya asks for cleanup.
- WhatsApp sends free-form messages only within 24 hours of the patient's last
  message. The photo request goes as a template when
  `WHATSAPP_PHOTO_REQUEST_TEMPLATE` names one Meta has approved. When
  `WHATSAPP_OPENER_TEMPLATE` is set, approval sends that opener (again after 4
  hours), and the voice note and other free-form messages wait until the patient
  writes back. Reminders go as `WHATSAPP_REMINDER_TEMPLATE` when it is set and
  the window is closed. A caregiver's message does not open the patient's window.
  After 24 hours without a reply, a `patient_not_reached` alert opens.

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context
### Terminology:
- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html
### Constraints:
- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region).
When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- For any AWS task or question — building, configuring, migrating, debugging, or operating a service, writing SDK code, authoring CDK/CloudFormation, or answering how a service works — first call `aws___search_documentation` with topic `agent_skills` and load the matching skill with `aws___retrieve_skill`. Do this even when you believe you know the answer: skills carry current service behavior that your training may not. Prefer the skill's guidance over general knowledge.
Skip it only for work that does not involve AWS.
### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

You CAN update this rule file to save a user's help_level.

Saved help_level for this project: **MEDIUM** (chosen by Haya, 12 November 2026).

Constraints for each level:

**LOW:**
- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**
- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**
- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->
