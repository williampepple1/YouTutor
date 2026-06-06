variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name (used for resource naming)"
  type        = string
  default     = "yoututor"
}

variable "frontend_dir" {
  description = "Path to frontend static files"
  type        = string
  default     = "../static"
}

variable "lambda_zip" {
  description = "Path to the Lambda deployment zip"
  type        = string
  default     = "../lambda.zip"
}

variable "domain_name" {
  description = "Custom domain name (leave empty to use CloudFront default)"
  type        = string
  default     = ""
}

variable "use_cloudfront" {
  description = "Whether to create a CloudFront distribution (requires AWS account verification)"
  type        = bool
  default     = false
}
