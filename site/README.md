# stasrift.com static site

Deploy this `site/` directory directly to Cloudflare Pages.

Build command: none
Output directory: `site`

The main product page preserves the original static design. No analytics or third-party JavaScript is added.

`review.html` is a business inquiry form using first-party `review.js`. It sends bounded JSON to the separate ARKOSOM intake Worker over HTTPS. It does not accept datasets, create engagements or invoices, or send inquiries to AI. The Worker validates consent and fields, rate limits submissions, and stores inquiries in private D1 storage. Billing and customer processing remain disabled. A receipt is shown on successful submission; email acknowledgments are not enabled.

The private Operator Worker, authentication configuration, database, and operational documentation are maintained separately from this public repository. Its live authenticated checks and production engagement activation require additional verification.
