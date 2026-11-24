#!/usr/bin/env bash
# Ship the current working tree to the demo instance and restart the stack.
# Usage: deploy/aws/deploy.sh   (after provision.sh)
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_PROFILE="${AWS_PROFILE:-hawlak}" AWS_REGION="${AWS_REGION:-eu-north-1}" AWS_PAGER=""

NAME=hawlak-demo
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="$NAME-deploy-$ACCOUNT-$AWS_REGION"
INSTANCE=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" Name=instance-state-name,Values=running \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
RELEASE=$(date -u +%Y%m%d-%H%M%S)
ARCHIVE=$(mktemp -d)/hawlak.tgz

# Source only: no .env, dependencies, caches or iCloud duplicate files ("name 2.ext").
COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czf "$ARCHIVE" \
  --exclude node_modules --exclude .venv --exclude dist --exclude __pycache__ \
  --exclude .pytest_cache --exclude .ruff_cache --exclude '* 2*' --exclude '.env' --exclude '*.log' \
  package.json package-lock.json tsconfig.base.json docker-compose.aws.yml \
  apps packages deploy fixtures
aws s3 cp "$ARCHIVE" "s3://$BUCKET/deployments/$RELEASE/source.tgz" --only-show-errors
echo "Uploaded release $RELEASE ($(du -h "$ARCHIVE" | cut -f1)); building on ${INSTANCE}..."

deploy/aws/ssm_run.sh "$INSTANCE" "hawlak: deploy $RELEASE" <<SCRIPT
set -euo pipefail
export AWS_REGION=$AWS_REGION
mkdir -p /opt/hawlak/releases && cd /opt/hawlak/releases
aws s3 cp s3://$BUCKET/deployments/$RELEASE/source.tgz /tmp/hawlak-$RELEASE.tgz --only-show-errors
mkdir -p $RELEASE && tar -xzf /tmp/hawlak-$RELEASE.tgz -C $RELEASE && rm /tmp/hawlak-$RELEASE.tgz
aws ssm get-parameter --name /hawlak/demo/env --with-decryption --query Parameter.Value --output text > $RELEASE/.env
chmod 600 $RELEASE/.env
ln -sfn /opt/hawlak/releases/$RELEASE /opt/hawlak/current
cd /opt/hawlak/current
PROFILES=""; grep -q '^HAWLAK_AGENT_CONTROL_URL=' .env && PROFILES="--profile voice"
docker compose -f docker-compose.aws.yml \$PROFILES up -d --build --remove-orphans
docker compose -f docker-compose.aws.yml ps --format '{{.Service}}: {{.Status}}'
ls -1dt /opt/hawlak/releases/*/ | tail -n +4 | xargs -r rm -rf
docker image prune -f >/dev/null
SCRIPT
