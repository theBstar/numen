import { type LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({ icon: Icon, title, description, action, secondaryAction }: EmptyStateProps) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center justify-center py-16 text-center">
        <div className="rounded-full bg-surface-100 p-4 mb-4">
          <Icon className="h-8 w-8 text-surface-400" />
        </div>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-sm text-surface-500 max-w-sm mb-6">{description}</p>
        {action && (
          <Button onClick={action.onClick}>{action.label}</Button>
        )}
        {secondaryAction && (
          <button
            onClick={secondaryAction.onClick}
            className="mt-3 text-sm text-primary-600 hover:text-primary-700 hover:underline"
          >
            {secondaryAction.label}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
