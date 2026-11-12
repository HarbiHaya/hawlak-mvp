# Hawlak care-transition language

Hawlak coordinates an approved discharge referral across the hospital, an integrated-care program, the patient, and an authorized caregiver.

## Care objects

**Discharge Referral**:
The issued hospital documents and minimum routing details sent to start a Hawlak episode, including patient contact, language, pathway, and caregiver choice.
_Avoid_: Upload, insurance file, raw case

**Approved Discharge Plan**:
The reviewed patient-facing facts that govern communication after discharge. The medication plan is one section of this plan.
_Avoid_: AI summary, generated plan

**Care Episode**:
The limited period during which Hawlak coordinates approved discharge communication, medication support, follow-up calls, caregiver status, and clinical exceptions.
_Avoid_: Claim, admission, customer journey

**Communication Packet**:
The reviewed set of patient-facing transcripts, exact voice content, call scripts, schedules, and channel assignments derived from the Approved Discharge Plan.
_Avoid_: AI output, message bundle

**Approved Medication Image**:
The exact hospital, pharmacy, catalogue, or fallback patient image that a Medication Reviewer has linked to one approved medication-plan item for use in reminders.
_Avoid_: AI-approved image, adherence proof

**Home Medication Confirmation**:
The fallback review used only when no verified image is available or the actual box at home must be checked. A Medication Reviewer compares the patient's photo with the approved medication-plan item.
_Avoid_: Mandatory photo collection, image classification approval

**Red-Flag Event**:
A patient answer or observation that meets an approved pathway rule for human clinical review or transfer.
_Avoid_: AI diagnosis, emergency prediction

## Organizations and roles

**Program Sponsor**:
The insurer, hospital, or integrated-care program that funds the Hawlak service and receives approved program reporting.
_Avoid_: Clinical approver, care team

**Service Eligibility Decision**:
The insurer's recorded decision that a patient is covered or accepted for a Hawlak pathway. It does not approve clinical content.
_Avoid_: Clinical approval, patient approval

**Integrated Care Clinical Team**:
The licensed clinicians and authorized case managers who operate the follow-up pathway for the Program Sponsor under an approved care arrangement.
_Avoid_: Insurance staff, payer user

**Hospital Discharge Team**:
The hospital professionals authorized to send the issued documents and minimum routing details in the Discharge Referral.
_Avoid_: Doctor side

**Medication Reviewer**:
A pharmacist or other licensed professional authorized by the pathway to approve medication content and the Home Medication Set.
_Avoid_: Insurance approver, image approver

**Clinical Responder**:
The licensed professional assigned to assess a Red-Flag Event, transfer a call, contact the patient, or return the case to the hospital.
_Avoid_: Agent, bot operator

**Program Analyst**:
A user who reviews aggregated operational and outcome measures without routine access to identifiable clinical records.
_Avoid_: Full-report user

## Patient support

**Patient Name**:
The patient's issued or registered name used to identify the Care Episode. The POC uses a synthetic full name.
_Avoid_: Patient alias, family nickname

**Preferred Form of Address**:
An optional name or form of address found in the hospital's source notes, such as a kunya. It may guide spoken communication but does not replace the Patient Name.
_Avoid_: Legal name, patient identifier

**Patient-Reported Medication Status**:
The patient's `taken`, `not yet`, or no-response state for a scheduled reminder. It does not prove ingestion or adherence.
_Avoid_: Verified dose, adherence confirmation

**Discharge Voice Note**:
The one-time, minimized patient-facing audio summary of approved discharge actions and warning signs.
_Avoid_: Full discharge summary, clinical record

**Medication Reminder Packet**:
A static, versioned bundle that links one approved medication item to its approved image, patient-facing instruction, reminder audio, and response choices.
_Avoid_: Dynamic reminder, AI medication advice

**Medication Image Checklist**:
The reviewed list that links each medication-plan item to the image Hawlak may send to the patient.
_Avoid_: Image gallery, AI match

**Conversational Call Plan**:
The approved schedule, question order, permitted clarifications, stop rules, urgent instructions, transfer group, retry rules, and fallback for follow-up calls in one Care Episode.
_Avoid_: Free-form AI call, call settings

**Caregiver Status Projection**:
The minimum patient-authorized view of reminder response, contact status, and follow-up state shown to a caregiver. It is not the clinical record.
_Avoid_: Family dashboard record, shared patient file

**Caregiver Authorization**:
The patient's recorded choice of caregiver, permitted status, channel, duration, and withdrawal route.
_Avoid_: Family access, next-of-kin access
