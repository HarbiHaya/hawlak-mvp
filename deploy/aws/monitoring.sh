#!/usr/bin/env bash
# CloudWatch monitoring for the Hawlak demo, in the project's selected Region. Safe to re-run.
#
#   container logs -> log group /hawlak/demo (docker awslogs driver, see docker-compose.aws.yml)
#   metric filters -> Hawlak/Errors, Hawlak/DeliveryFailed
#   alarms (errors, failed deliveries, instance status, CPU) -> SNS topic hawlak-demo-alerts
#   dashboard hawlak-demo
#
# Usage: deploy/aws/monitoring.sh                       (then deploy.sh to switch the log driver)
#        ALERT_EMAIL=you@example.com deploy/aws/monitoring.sh   (also subscribes that email)
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_PROFILE="${AWS_PROFILE:-hawlak}" AWS_REGION="${AWS_REGION:-eu-north-1}" AWS_PAGER=""

NAME=hawlak-demo
GROUP=/hawlak/demo
RETENTION_DAYS=14
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
INSTANCE=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)

echo "== Log group $GROUP ($RETENTION_DAYS days)"
if [ -z "$(aws logs describe-log-groups --log-group-name-prefix "$GROUP" \
  --query "logGroups[?logGroupName=='$GROUP'].logGroupName" --output text)" ]; then
  aws logs create-log-group --log-group-name "$GROUP" --tags Project=$NAME
fi
aws logs put-retention-policy --log-group-name "$GROUP" --retention-in-days $RETENTION_DAYS

echo "== Instance role may write to $GROUP only"
aws iam put-role-policy --role-name "$NAME-ec2-role" --policy-name "$NAME-logs" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{\"Effect\": \"Allow\", \"Action\": [\"logs:CreateLogStream\", \"logs:PutLogEvents\"],
    \"Resource\": \"arn:aws:logs:$AWS_REGION:$ACCOUNT:log-group:$GROUP:log-stream:*\"}]
}"

echo "== Metric filters"
# Python tracebacks and ERROR/CRITICAL lines from every container.
aws logs put-metric-filter --log-group-name "$GROUP" --filter-name errors \
  --filter-pattern '?ERROR ?CRITICAL ?Traceback' --metric-transformations \
  metricName=Errors,metricNamespace=Hawlak,metricValue=1,defaultValue=0
# journey_delivery logs one line per failed WhatsApp send or call dispatch.
aws logs put-metric-filter --log-group-name "$GROUP" --filter-name delivery-failed \
  --filter-pattern '"Delivery run failed"' --metric-transformations \
  metricName=DeliveryFailed,metricNamespace=Hawlak,metricValue=1,defaultValue=0

echo "== Alert topic"
TOPIC=$(aws sns create-topic --name "$NAME-alerts" --tags Key=Project,Value=$NAME \
  --query TopicArn --output text)
if [ -n "${ALERT_EMAIL:-}" ]; then
  aws sns subscribe --topic-arn "$TOPIC" --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
  echo "Subscribed; confirm the email AWS just sent before alerts arrive."
fi

echo "== Alarms"
alarm() {  # name description namespace metric stat period periods datapoints threshold missing [dimensions]
  aws cloudwatch put-metric-alarm --alarm-name "$NAME-$1" --alarm-description "$2" \
    --namespace "$3" --metric-name "$4" --statistic "$5" --period "$6" \
    --evaluation-periods "$7" --datapoints-to-alarm "$8" --threshold "$9" \
    --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data "${10}" \
    ${11:+--dimensions "${11}"} --alarm-actions "$TOPIC" --ok-actions "$TOPIC"
}
# ponytail: starting thresholds; tune once there is a week of real traffic.
alarm errors "5+ error lines in 5 minutes across the stack" Hawlak Errors Sum 300 1 1 5 notBreaching
alarm delivery-failed "A WhatsApp send or call dispatch failed" Hawlak DeliveryFailed Sum 300 1 1 1 notBreaching
# Missing data while the instance is stopped on purpose is not an alarm.
alarm instance-status "EC2 status check failing" AWS/EC2 StatusCheckFailed Maximum 60 2 2 1 notBreaching \
  "Name=InstanceId,Value=$INSTANCE"
alarm cpu-high "CPU at 85%+ for 15 minutes" AWS/EC2 CPUUtilization Average 300 3 3 85 notBreaching \
  "Name=InstanceId,Value=$INSTANCE"

echo "== Dashboard $NAME"
cat > /tmp/hawlak-dashboard.json <<JSON
{"widgets": [
  {"type": "alarm", "x": 0, "y": 0, "width": 24, "height": 3, "properties": {"title": "Alarms",
    "alarms": ["arn:aws:cloudwatch:$AWS_REGION:$ACCOUNT:alarm:$NAME-errors",
               "arn:aws:cloudwatch:$AWS_REGION:$ACCOUNT:alarm:$NAME-delivery-failed",
               "arn:aws:cloudwatch:$AWS_REGION:$ACCOUNT:alarm:$NAME-instance-status",
               "arn:aws:cloudwatch:$AWS_REGION:$ACCOUNT:alarm:$NAME-cpu-high"]}},
  {"type": "metric", "x": 0, "y": 3, "width": 12, "height": 6, "properties": {"title": "Errors and failed deliveries",
    "region": "$AWS_REGION", "view": "timeSeries", "stat": "Sum", "period": 300,
    "metrics": [["Hawlak", "Errors"], ["Hawlak", "DeliveryFailed"]]}},
  {"type": "metric", "x": 12, "y": 3, "width": 12, "height": 6, "properties": {"title": "Instance",
    "region": "$AWS_REGION", "view": "timeSeries", "period": 300,
    "metrics": [["AWS/EC2", "CPUUtilization", "InstanceId", "$INSTANCE", {"stat": "Average"}],
                ["AWS/EC2", "StatusCheckFailed", "InstanceId", "$INSTANCE", {"stat": "Maximum", "yAxis": "right"}]]}},
  {"type": "log", "x": 0, "y": 9, "width": 24, "height": 8, "properties": {"title": "Recent errors and failures",
    "region": "$AWS_REGION", "view": "table",
    "query": "SOURCE '$GROUP' | fields @timestamp, @logStream, @message | filter @message like /ERROR|CRITICAL|Traceback|Delivery run failed/ | sort @timestamp desc | limit 50"}}
]}
JSON
aws cloudwatch put-dashboard --dashboard-name "$NAME" --dashboard-body file:///tmp/hawlak-dashboard.json >/dev/null
rm /tmp/hawlak-dashboard.json

echo
echo "Dashboard: https://$AWS_REGION.console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#dashboards/dashboard/$NAME"
echo "Logs:      https://$AWS_REGION.console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups/log-group/\$252Fhawlak\$252Fdemo"
