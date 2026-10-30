import { Compass } from "lucide-react";
import { ButtonLink } from "../components/ui/Button";
import { Card, EmptyState } from "../components/ui/primitives";

export function NotFoundPage() {
  return (
    <Card>
      <EmptyState
        icon={<Compass className="size-6" />}
        title="Page not found"
        description="The page you're looking for doesn't exist or has moved."
        action={<ButtonLink to="/">Go to dashboard</ButtonLink>}
      />
    </Card>
  );
}
