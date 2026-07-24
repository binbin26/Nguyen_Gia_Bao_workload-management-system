import DOMPurify from "dompurify";
import { useMemo } from "react";

const SANITIZE_CONFIG = Object.freeze({
  // Allow only the small HTML subset the product actually needs. React escapes
  // strings by default; use this component only when rich HTML is intentional.
  ALLOWED_TAGS: [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "ul",
    "ol",
    "li",
    "blockquote",
    "code",
    "a",
  ],
  ALLOWED_ATTR: ["href", "title"],
  ALLOW_DATA_ATTR: false,
  FORBID_TAGS: ["script", "style", "iframe", "object", "embed", "form"],
  FORBID_ATTR: ["style"],
});

export function sanitizeUserHtml(dirtyHtml) {
  return DOMPurify.sanitize(String(dirtyHtml ?? ""), SANITIZE_CONFIG);
}

/**
 * The only approved boundary for intentionally rendering user-authored HTML.
 * Do not modify the sanitized markup afterward; doing so can reintroduce XSS.
 */
export default function SafeHtml({ html, className }) {
  const cleanHtml = useMemo(() => sanitizeUserHtml(html), [html]);

  return (
    <div
      className={className}
      // Safe because cleanHtml is produced immediately above by DOMPurify.
      dangerouslySetInnerHTML={{ __html: cleanHtml }}
    />
  );
}
