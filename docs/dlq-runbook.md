*# GuardDuty Threat Pipeline — DLQ Runbook*



*## 1. Purpose*



*This runbook describes how to investigate and recover GuardDuty findings that fail repeated processing and are moved to the SQS dead-letter queue (DLQ).*



*## 2. Alert condition*



*The CloudWatch alarm `guardduty-dlq-has-messages` monitors the DLQ's `ApproximateNumberOfMessagesVisible` metric.*



*The alarm threshold is one visible message over a 60-second evaluation period. The alarm action publishes a notification to the configured SNS topic.*



*## 3. Initial response*



*1. Acknowledge the alert and record the time it was received.*

*2. Check the CloudWatch alarm state and relevant Lambda logs.*

*3. Identify the affected finding and SQS message.*

*4. Determine whether the failure is caused by malformed input, configuration, permissions, a dependency outage, or an application defect.*

*5. Preserve the message and relevant logs before attempting recovery.*



*## 4. Recovery procedure*



*1. Fix the underlying cause before replaying messages.*

*2. Inspect the message body and verify that it contains a valid GuardDuty/EventBridge finding.*

*3. Confirm that the finding's account, region, ID, and severity fields are valid.*

*4. Use an approved, controlled redrive process after validating the fix.*

*5. Monitor processing results and verify that the message is handled successfully.*

*6. Confirm that the DLQ backlog decreases and the alarm returns to a non-alarm state.*



*## 5. Duplicate and safety controls*



*- Do not delete DLQ messages before preserving evidence and understanding the failure.*

*- Confirm idempotency behavior before replaying a message.*

*- Do not assume that an alert was never sent merely because a message was retried.*

*- Avoid broad automated remediation until its permissions, safeguards, and rollback behavior have been tested.*



*## 6. Closure criteria*



*- The failure cause is documented.*

*- The underlying defect or configuration issue is corrected.*

*- Recovered messages are processed or explicitly dispositioned.*

*- No unexpected duplicate notifications or side effects are observed.*

*- The alarm state and incident notes are updated.*



*## 7. Current implementation limitations*



*Local tests verify application behavior using synthetic events and test doubles. Live SQS redrive, CloudWatch alarm transitions, SNS delivery, and deployed AWS permissions must be verified separately before claiming end-to-end production readiness.*
