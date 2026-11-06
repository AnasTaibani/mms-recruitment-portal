import { useState } from "react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", onConfirm, reason, reasonLabel = "Reason", dateLabel, destructive, testid = "confirm" }) {
  const [text, setText] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const blocked = (reason && !text.trim()) || (dateLabel && !date);
  const go = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onConfirm({ reason: text, date });
      setText(""); setDate("");
      onOpenChange(false);
    } finally { setBusy(false); }
  };
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid={`${testid}-dialog`}>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription>{description}</AlertDialogDescription>}
        </AlertDialogHeader>
        {dateLabel && (
          <div className="space-y-1.5"><Label className="text-xs">{dateLabel} *</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} data-testid={`${testid}-date`} /></div>
        )}
        {reason && (
          <div className="space-y-1.5"><Label className="text-xs">{reasonLabel} *</Label><Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} data-testid={`${testid}-reason`} /></div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel data-testid={`${testid}-cancel`}>Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={blocked || busy} onClick={go} className={destructive ? "bg-rose-600 hover:bg-rose-700" : ""} data-testid={`${testid}-ok`}>{confirmLabel}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
