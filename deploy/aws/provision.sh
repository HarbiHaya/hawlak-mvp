#!/usr/bin/env bash
# One-time AWS setup for the Hawlak demo in the project's selected Region. Safe to re-run:
# each step reuses what already exists. Run deploy.sh afterwards to ship the code.
#
#   EC2 (Docker Compose) <- CloudFront (HTTPS) ; files in S3 via the instance role ;
#   secrets in SSM Parameter Store /hawlak/demo/env ; access via Session Manager (no SSH).
set -euo pipefail
cd "$(dirname "$0")/../.."
export AWS_PROFILE="${AWS_PROFILE:-hawlak}" AWS_REGION="${AWS_REGION:-eu-north-1}"
export AWS_PAGER=""

NAME=hawlak-demo
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
DEPLOY_BUCKET="$NAME-deploy-$ACCOUNT-$AWS_REGION"
FILES_BUCKET="$NAME-files-$ACCOUNT-$AWS_REGION"
ROLE="$NAME-ec2-role"
PROFILE="$NAME-ec2-profile"
ENV_PARAM=/hawlak/demo/env
TAGS="Key=Name,Value=$NAME Key=Project,Value=$NAME"

echo "== S3 buckets (private, encrypted)"
for bucket in "$DEPLOY_BUCKET" "$FILES_BUCKET"; do
  aws s3api head-bucket --bucket "$bucket" 2>/dev/null || aws s3api create-bucket --bucket "$bucket" \
    --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
done

echo "== Instance role"
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name "$NAME-app" --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {\"Effect\": \"Allow\", \"Action\": \"s3:GetObject\", \"Resource\": \"arn:aws:s3:::$DEPLOY_BUCKET/deployments/*\"},
    {\"Effect\": \"Allow\", \"Action\": \"s3:ListBucket\", \"Resource\": \"arn:aws:s3:::$FILES_BUCKET\"},
    {\"Effect\": \"Allow\", \"Action\": [\"s3:GetObject\", \"s3:PutObject\"], \"Resource\": \"arn:aws:s3:::$FILES_BUCKET/*\"},
    {\"Effect\": \"Allow\", \"Action\": \"ssm:GetParameter\", \"Resource\": \"arn:aws:ssm:$AWS_REGION:$ACCOUNT:parameter$ENV_PARAM\"}
  ]
}"
if ! aws iam get-instance-profile --instance-profile-name "$PROFILE" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$PROFILE" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE" --role-name "$ROLE"
  sleep 10  # IAM propagation before run-instances
fi

echo "== Security group: port 80 from CloudFront only"
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NAME-web" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name "$NAME-web" --description "Hawlak demo: HTTP from CloudFront" \
    --vpc-id "$VPC" --query GroupId --output text)
fi
CF_PREFIX=$(aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query 'PrefixLists[0].PrefixListId' --output text)
OPEN=$(aws ec2 describe-security-groups --group-ids "$SG" --query 'SecurityGroups[0].IpPermissions' --output json)
if [ "$OPEN" != "[]" ]; then
  aws ec2 revoke-security-group-ingress --group-id "$SG" --ip-permissions "$OPEN" >/dev/null
fi
aws ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
  "IpProtocol=tcp,FromPort=80,ToPort=80,PrefixListIds=[{PrefixListId=$CF_PREFIX,Description=CloudFront}]" >/dev/null

echo "== EC2 instance"
INSTANCE=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)
if [ "$INSTANCE" = "None" ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
    --query Parameter.Value --output text)
  INSTANCE=$(aws ec2 run-instances --image-id "$AMI" --instance-type m7i-flex.large \
    --iam-instance-profile "Name=$PROFILE" --security-group-ids "$SG" \
    --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled \
    --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true}' \
    --user-data '#!/bin/bash
dnf install -y docker && systemctl enable --now docker' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=Project,Value=$NAME}]" \
    --query 'Instances[0].InstanceId' --output text)
  aws ec2 wait instance-running --instance-ids "$INSTANCE"
fi
# Containers reach the instance role through IMDSv2, which needs a hop limit of 2.
aws ec2 modify-instance-metadata-options --instance-id "$INSTANCE" \
  --http-tokens required --http-put-response-hop-limit 2 >/dev/null

echo "== Elastic IP (stable CloudFront origin)"
ALLOC=$(aws ec2 describe-addresses --filters "Name=tag:Name,Values=$NAME" \
  --query 'Addresses[0].AllocationId' --output text)
if [ "$ALLOC" = "None" ]; then
  ALLOC=$(aws ec2 allocate-address --domain vpc --tag-specifications \
    "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME},{Key=Project,Value=$NAME}]" \
    --query AllocationId --output text)
fi
aws ec2 associate-address --allocation-id "$ALLOC" --instance-id "$INSTANCE" >/dev/null
IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp' --output text)
ORIGIN="ec2-${IP//./-}.$AWS_REGION.compute.amazonaws.com"

echo "== CloudFront distribution"
DOMAIN=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='$NAME'].DomainName | [0]" --output text)
if [ "$DOMAIN" = "None" ] || [ -z "$DOMAIN" ]; then
  # ponytail: CloudFront -> EC2 is plain HTTP (synthetic data only); add an origin
  # certificate and https-only before any real patient data.
  CONFIG=$(cat <<JSON
{
  "CallerReference": "$NAME-$(date +%s)",
  "Comment": "$NAME",
  "Enabled": true,
  "PriceClass": "PriceClass_100",
  "HttpVersion": "http2and3",
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "ec2", "DomainName": "$ORIGIN",
    "CustomOriginConfig": {"HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
      "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 5,
      "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]}}
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "ec2", "ViewerProtocolPolicy": "redirect-to-https", "Compress": true,
    "AllowedMethods": {"Quantity": 7, "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}},
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  },
  "CacheBehaviors": {"Quantity": 1, "Items": [{
    "PathPattern": "/assets/*", "TargetOriginId": "ec2", "ViewerProtocolPolicy": "redirect-to-https",
    "Compress": true,
    "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}},
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }]}
}
JSON
)
  DOMAIN=$(aws cloudfront create-distribution --distribution-config "$CONFIG" \
    --query Distribution.DomainName --output text)
fi

echo "== Runtime secrets in SSM ($ENV_PARAM)"
if ! aws ssm get-parameter --name "$ENV_PARAM" >/dev/null 2>&1; then
  # Built once from the local .env so database passwords never rotate under a live volume.
  ENV_FILE=$(DOMAIN="$DOMAIN" FILES_BUCKET="$FILES_BUCKET" python3 deploy/aws/runtime_env.py .env)
  aws ssm put-parameter --name "$ENV_PARAM" --type SecureString --value "$ENV_FILE" \
    --tags $TAGS >/dev/null
fi

echo "== Docker tooling on the instance (compose needs a recent buildx)"
COMMAND=$(deploy/aws/ssm_run.sh "$INSTANCE" "hawlak: install compose and buildx" <<'SCRIPT'
set -euo pipefail
dnf install -y docker && systemctl enable --now docker
mkdir -p /usr/local/lib/docker/cli-plugins && cd /usr/local/lib/docker/cli-plugins
curl -fsSL -o docker-compose https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64
curl -fsSL -o /tmp/buildx-release.json https://api.github.com/repos/docker/buildx/releases/latest
BX=$(grep -m1 '"tag_name"' /tmp/buildx-release.json | cut -d'"' -f4)
curl -fsSL -o docker-buildx "https://github.com/docker/buildx/releases/download/$BX/buildx-$BX.linux-amd64"
chmod +x docker-compose docker-buildx
docker compose version && docker buildx version
SCRIPT
)
echo "$COMMAND"

echo
echo "Instance:   $INSTANCE ($IP)"
echo "Dashboard:  https://$DOMAIN  (CloudFront takes a few minutes to deploy)"
