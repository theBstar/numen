import { ArrowRight } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/StatusBadge";

interface StatusTransitionDialogProps {
  open: boolean;
  currentStatus: string;
  targetStatus: string;
  prName: string;
  onConfirm: () => void;
  onSkip: () => void;
}

export function StatusTransitionDialog({
  open,
  currentStatus,
  targetStatus,
  prName,
  onConfirm,
  onSkip,
}: StatusTransitionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onSkip(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Update task status?</DialogTitle>
          <DialogDescription>
            The linked PR <span className="font-medium text-surface-700">{prName}</span> suggests
            a status change for this task.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center justify-center gap-3 py-4">
          <StatusBadge status={currentStatus} />
          <ArrowRight size={16} className="text-surface-400" />
          <StatusBadge status={targetStatus} />
        </div>
        <DialogFooter>
          <button onClick={onSkip} className="btn-secondary text-sm">
            Keep current status
          </button>
          <button onClick={onConfirm} className="btn-primary text-sm">
            Update status
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
