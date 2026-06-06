terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  backend "s3" {
    bucket = "yoututor-terraform-state-628711466156"
    key    = "terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# ── S3 Bucket for frontend ────────────────────────────────────────
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.app_name}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "frontend" {
  count  = var.use_cloudfront ? 1 : 0
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2008-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontRead"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.main[0].arn
        }
      }
    }]
  })
}

resource "aws_s3_object" "frontend_files" {
  for_each     = fileset(var.frontend_dir, "**/*")
  bucket       = aws_s3_bucket.frontend.id
  key          = each.value
  source       = "${var.frontend_dir}/${each.value}"
  etag         = filemd5("${var.frontend_dir}/${each.value}")
  content_type = lookup({
    html = "text/html",
    css  = "text/css",
    js   = "application/javascript",
    json = "application/json",
    svg  = "image/svg+xml",
    png  = "image/png",
    jpg  = "image/jpeg",
    ico  = "image/x-icon",
  }, split(".", each.value)[length(split(".", each.value)) - 1], "application/octet-stream")
}

# ── Lambda IAM Role ───────────────────────────────────────────────
resource "aws_iam_role" "lambda" {
  name = "${var.app_name}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── Lambda Function ───────────────────────────────────────────────
resource "aws_lambda_function" "backend" {
  filename         = var.lambda_zip
  function_name    = "${var.app_name}-backend"
  role             = aws_iam_role.lambda.arn
  handler          = "deploy.lambda.handler.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 512
  source_code_hash = filebase64sha256(var.lambda_zip)

  environment {
    variables = {
      PORT = "8080"
    }
  }
}

# ── API Gateway HTTP API ──────────────────────────────────────────
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.app_name}-api"
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                    = aws_apigatewayv2_api.main.id
  integration_type          = "AWS_PROXY"
  integration_uri           = aws_lambda_function.backend.invoke_arn
  payload_format_version    = "2.0"
}

resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ── API Gateway Custom Domain (optional) ──────────────────────────
# Uncomment and set your domain name if you have one:
# resource "aws_apigatewayv2_domain_name" "api" {
#   domain_name = "api.${var.domain_name}"
#   domain_name_configuration {
#     certificate_arn = aws_acm_certificate.main.arn
#     endpoint_type   = "REGIONAL"
#     security_policy = "TLS_1_2"
#   }
# }

# ── CloudFront Distribution (optional — requires AWS account verification) ─
resource "aws_cloudfront_origin_access_identity" "main" {
  count     = var.use_cloudfront ? 1 : 0
  comment   = "${var.app_name} OAI"
}

resource "aws_cloudfront_distribution" "main" {
  count       = var.use_cloudfront ? 1 : 0
  enabled     = true
  price_class = "PriceClass_100"
  aliases     = var.domain_name != "" ? [var.domain_name] : []

  origin {
    domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id   = "S3Frontend"
    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.main[0].cloudfront_access_identity_path
    }
  }

  origin {
    domain_name = replace(aws_apigatewayv2_api.main.api_endpoint, "https://", "")
    origin_id   = "APIGateway"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "S3Frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    default_ttl            = 3600
    max_ttl                = 86400
    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "APIGateway"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true
    default_ttl            = 0
    max_ttl                = 0
    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies {
        forward = "all"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  # Custom domain SSL (uncomment if you have a domain)
  # viewer_certificate {
  #   acm_certificate_arn = aws_acm_certificate.main.arn
  #   ssl_support_method  = "sni-only"
  # }
}

# ── Data Sources ──────────────────────────────────────────────────
data "aws_caller_identity" "current" {}

# ── Outputs ───────────────────────────────────────────────────────
output "cloudfront_url" {
  value = var.use_cloudfront ? "https://${aws_cloudfront_distribution.main[0].domain_name}" : "CloudFront not deployed (set use_cloudfront=true after AWS account verification)"
}

output "cloudfront_id" {
  value = var.use_cloudfront ? aws_cloudfront_distribution.main[0].id : ""
}

output "api_url" {
  value = aws_apigatewayv2_api.main.api_endpoint
}

output "frontend_url" {
  value = "https://${aws_s3_bucket.frontend.bucket_regional_domain_name}"
}

output "s3_bucket" {
  value = aws_s3_bucket.frontend.bucket
}

output "lambda_function" {
  value = aws_lambda_function.backend.function_name
}
