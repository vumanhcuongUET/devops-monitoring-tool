# Infrastructure Security Review Skill

Review infrastructure code (Terraform, CloudFormation, Ansible, etc.) for security vulnerabilities and best practices.

## What to Check

### 1. Cloud Credentials

**Hardcoded Credentials**
```hcl
# ❌ VULNERABLE - Credentials in code
resource "aws_db_instance" "default" {
  username = "admin"
  password = "hardcoded-password-123"  # Exposed in code!
}

# ✅ SECURE - Random generation or vault
resource "random_password" "db_password" {
  length = 32
  special = true
}

resource "aws_db_instance" "default" {
  username = "admin"
  password = random_password.db_password.result
}

# Or use Vault/Secrets Manager
data "vault_generic_secret" "db_creds" {
  path = "database/prod/credentials"
}

resource "aws_db_instance" "default" {
  password = data.vault_generic_secret.db_creds.data["password"]
}
```

### 2. S3 Bucket Security

**Public Access**
```hcl
# ❌ VULNERABLE - Public bucket
resource "aws_s3_bucket" "logs" {
  acl = "public-read"  # Anyone can read!

  # Or without proper block public access
  # Public access enabled by default
}

# ✅ SECURE - Private bucket with encryption
resource "aws_s3_bucket" "logs" {
  # No ACL or acl = "private"

  # Block all public access
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
```

### 3. Network Security

**Open Security Groups**
```hcl
# ❌ VULNERABLE - Open to world
resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # SSH from anywhere!
  }
}

# ✅ SECURE - Restricted access
resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]  # Only internal network
  }

  # Or use security group IDs instead of CIDR
  ingress {
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.bastion.id]  # Only from bastion
  }
}
```

**Missing VPC Flow Logs**
```hcl
# ❌ BAD - No network monitoring

# ✅ GOOD - Flow logs enabled
resource "aws_flow_log" "main" {
  iam_role_arn         = aws_iam_role.flow_logs.arn
  log_destination      = aws_cloudwatch_log_group.flow_logs.arn
  traffic_type         = "ALL"
  vpc_id               = aws_vpc.main.id
}
```

### 4. Instance Security

**Instances in Public Subnet**
```hcl
# ❌ VULNERABLE - Database in public subnet
resource "aws_db_subnet_group" "default" {
  subnet_ids = aws_subnet.public[*].id  # Public subnets!
}

# ✅ SECURE - Private subnets
resource "aws_db_subnet_group" "default" {
  subnet_ids = aws_subnet.private[*].id
}
```

**Missing IMDSv2**
```hcl
# ❌ BAD - Using IMDSv1 (vulnerable to SSRF)
resource "aws_instance" "web" {
  # Default is IMDSv1
}

# ✅ SECURE - Require IMDSv2
resource "aws_instance" "web" {
  metadata_options {
    http_tokens                 = "required"  # IMDSv2 required
    http_put_response_hop_limit = 1
  }
}
```

### 5. Secrets Management

**Secrets in Plain Text**
```yaml
# ❌ VULNERABLE - Secrets in config
apiVersion: v1
kind: Secret
metadata:
  name: api-secret
type: Opaque
stringData:
  password: "hardcoded-password"

# ✅ SECURE - External secrets manager
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-secret
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: api-secret
  data:
  - secretKey: password
    remoteRef:
      key: prod/api/password
```

### 6. IAM & Permissions

**Overly Permissive Policies**
```json
// ❌ VULNERABLE - Wildcard permissions
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "*",
    "Resource": "*"
  }]
}

// ✅ SECURE - Least privilege
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:GetObject",
      "s3:PutObject"
    ],
    "Resource": "arn:aws:s3:::my-bucket/*"
  }]
}
```

**No MFA for Sensitive Operations**
```json
// ❌ BAD - No MFA requirement

// ✅ GOOD - MFA required
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Deny",
    "Action": [
      "iam:DeleteUser",
      "iam:CreateAccessKey"
    ],
    "Resource": "*",
    "Condition": {
      "Bool": {
        "aws:MultiFactorAuthPresent": "false"
      }
    }
  }]
}
```

### 7. Encryption

**Unencrypted Volumes**
```hcl
# ❌ BAD - Unencrypted EBS
resource "aws_ebs_volume" "data" {
  # No encryption enabled
}

# ✅ SECURE - Encrypted by default
resource "aws_ebs_volume" "data" {
  encrypted = true
  kms_key_id = aws_kms_key.data.arn
}

# Or enable at account level
resource "aws_ebs_encryption_by_default" "main" {
  enabled = true
}
```

**Unencrypted RDS**
```hcl
# ❌ BAD - Unencrypted database
resource "aws_db_instance" "default" {
  # No encryption
}

# ✅ SECURE - Encrypted storage
resource "aws_db_instance" "default" {
  storage_encrypted = true
  kms_key_id       = aws_kms_key.rds.arn
}
```

### 8. Logging & Monitoring

**No CloudTrail**
```hcl
# ❌ BAD - No audit trail

# ✅ GOOD - CloudTrail enabled
resource "aws_cloudtrail" "main" {
  name = "main-trail"
  s3_bucket_name = aws_s3_bucket.logs.id

  event_selector {
    read_write_type = "All"
    include_management_events = true
  }

  is_multi_region_trail = true
}
```

**No GuardDuty**
```hcl
# ✅ GOOD - Threat detection
resource "aws_guardduty_detector" "main" {
  enable = true
}

resource "aws_guardduty_ipset" "trusted" {
  detector_id = aws_guardduty_detector.main.id
  ipset_id     = "trusted-set"
  location     = "https://s3.amazonaws.com/my-bucket/trusted-ips.json"
  activate     = true
}
```

### 9. Backup & Disaster Recovery

**No Automated Backups**
```hcl
# ❌ BAD - No backup configuration

# ✅ GOOD - Automated backups
resource "aws_db_instance" "default" {
  backup_retention_period = 30  # Keep 30 days
  backup_window       = "03:00-04:00"  # During low traffic

  # Enable PITR
  enabled_cloudwatch_logs_exports = ["postgresql"]
}
```

**No Cross-Region Replication**
```hcl
# ❌ BAD - Data in single region

# ✅ GOOD - Multi-region redundancy
resource "aws_s3_bucket" "primary" {
  region = "us-east-1"
}

resource "aws_s3_bucket_replication_configuration" "replication" {
  role = aws_iam_role.replication.arn
  bucket = aws_s3_bucket.primary.id

  rules {
    destination {
      bucket        = aws_s3_bucket.secondary.arn
      storage_class = "GLACIER"
    }
  }
}
```

### 10. Compliance & Governance

**No SCPs**
```json
// ❌ BAD - No organizational policies

// ✅ GOOD - Service Control Policies
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Deny",
    "Action": ["iam:CreateAccessKey"],
    "Resource": "*",
    "Condition": {
      "StringNotEquals": {
        "aws:PrincipalTag/JobFunction": ["Admin"]
      }
    }
  }]
}
```

**No Config Rules**
```hcl
// ✅ GOOD - Compliance monitoring
resource "aws_config_configuration_aggregator" "org" {
  name = "org-aggregator"

  account_aggregation_source {
    account_ids = [data.aws_caller_identity.current.account_id]
  }
}

resource "aws_config_rule" "s3-public-read" {
  name = "s3-public-read-prohibited"

  source {
    owner             = "AWS"
    source_identifier = "S3_BUCKET_PUBLIC_READ_PROHIBITED"
  }
}
```

### 11. Container Security

**Unrestricted Pod Security**
```yaml
# ❌ BAD - No pod security policies
# Any pod can run with any configuration

# ✅ GOOD - Pod security standards
apiVersion: v1
kind: Namespace
metadata:
  name: secure-namespace
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

### 12. GitOps Security

**Secrets in Git**
```yaml
# ❌ VULNERABLE - Secrets in repo
# secret.yaml in Git with plain text passwords

# ✅ SECURE - Sealed Secrets or External Secrets
# Commit encrypted secret to git
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: api-secret
spec:
  encryptedData:
    password: AgBy3g4... (encrypted)
```

### 13. CI/CD Security

**Unvalidated Terraform Plans**
```yaml
# ❌ BAD - Auto-apply without review
# CI/CD pipeline:
# terraform apply -auto-approve

# ✅ GOOD - Required approval
# CI/CD pipeline:
# terraform plan -out=tfplan
# terraform show -json tfplan > plan.json
# Run security checks on plan.json
# Require manual approval before apply
```

### 14. Cost Controls

**No Budgets**
```hcl
# ❌ BAD - No cost controls

# ✅ GOOD - Budget alerts
resource "aws_budgets_budget" "monthly" {
  name              = "monthly-budget"
  budget_type       = "COST"
  limit_amount      = "1000.0"
  limit_unit        = "USD"

  time_period {
    start = "2023-01-01"
    end   = "2087-12-31"
  }

  notification {
    comparison_operator = "GREATER_THAN"
    notification_type   = "ACTUAL"
    threshold_type      = "PERCENTAGE_OF_BUDGET"
    threshold           = 80
  }
}
```

### 15. High Availability

**Single Point of Failure**
```hcl
# ❌ BAD - Single instance
resource "aws_instance" "app" {
  count = 1  # Single point of failure!
}

# ✅ GOOD - Multi-AZ with ASG
resource "aws_autoscaling_group" "app" {
  min_size = 2
  max_size = 10
  desired_capacity = 3

  vpc_zone_identifier = aws_subnet.private[*].id

  health_check_type = "EC2"
}
```

## Review Checklist

For each infrastructure resource, check:

- [ ] No hardcoded credentials
- [ ] S3 buckets block public access
- [ ] S3 buckets encrypted at rest
- [ ] Security groups restrict access
- [ ] VPC flow logs enabled
- [ ] Instances in private subnets (where appropriate)
- [ ] IMDSv2 required
- [ ] Secrets from external managers (Vault, Secrets Manager)
- [ ] IAM policies follow least privilege
- [ ] MFA required for sensitive operations
- [ ] EBS volumes encrypted
- [ ] RDS encrypted
- [ ] CloudTrail enabled
- [ ] GuardDuty enabled
- [ ] Automated backups configured
- [ ] Cross-region replication for critical data
- [ ] Service Control Policies configured
- [ ] Config rules for compliance
- [ ] Pod security policies enforced
- [ ] Secrets encrypted in Git
- [ ] Terraform plans reviewed before apply
- [ ] Cost budgets configured
- [ ] High availability with multi-AZ
- [ ] Auto-scaling for resilience

## Output Format

```markdown
## Infrastructure Security Review: [resource/file]

### Critical
- [Issue] - [Security impact] - [Recommendation]

### High
- [Issue] - [Security impact] - [Recommendation]

### Medium
- [Issue] - [Security impact] - [Recommendation]

### Low
- [Issue] - [Security impact] - [Recommendation]

### Positive Patterns
+ [Good security practice found]
```
