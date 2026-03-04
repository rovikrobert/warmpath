import { Link } from "react-router-dom";

type MarketplaceVisibilityExplainerProps = {
  compact?: boolean;
  className?: string;
};

export default function MarketplaceVisibilityExplainer({
  compact = false,
  className = "",
}: MarketplaceVisibilityExplainerProps) {
  if (compact) {
    return (
      <p className={className}>
        Job seekers see anonymized listing fields only: company, role level, department, and connection strength.
        They never see names, emails, or LinkedIn profiles unless you approve the intro request.{" "}
        <Link to="/privacy#marketplace-visibility" className="text-primary hover:text-primary/90 hover:underline">
          Learn more
        </Link>
      </p>
    );
  }

  return (
    <div className={`rounded-lg border border-info/30 bg-info/10 p-4 ${className}`}>
      <p className="text-sm text-info">
        Job seekers see anonymized listing fields only: company, role level, department, and connection strength.
        They never see names, emails, or LinkedIn profiles unless you approve the intro request.
      </p>
      <Link
        to="/privacy#marketplace-visibility"
        className="mt-2 inline-block text-xs font-medium text-info/80 hover:text-info/70 hover:underline"
      >
        What is visible and when identity is disclosed
      </Link>
    </div>
  );
}
