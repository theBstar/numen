import { useRef } from "react";
import { Paperclip, Upload, Trash2, Download, Loader2, FileText, Image, File } from "lucide-react";
import { useAttachments } from "@/hooks/queries";
import { useUploadAttachment, useDeleteAttachment } from "@/hooks/mutations";
import { downloadAttachment } from "@/services/api";
import type { Attachment } from "@/types";

interface AttachmentListProps {
  taskId: string;
}

function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function getFileIcon(mimeType: string | null) {
  if (!mimeType) return File;
  if (mimeType.startsWith("image/")) return Image;
  if (mimeType.startsWith("text/") || mimeType.includes("pdf")) return FileText;
  return File;
}

export function AttachmentList({ taskId }: AttachmentListProps) {
  const { data, isLoading } = useAttachments(taskId);
  const upload = useUploadAttachment();
  const deleteAttach = useDeleteAttachment();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const attachments = data?.items ?? [];

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files?.length) return;
    for (const file of Array.from(files)) {
      upload.mutate({ taskId, file });
    }
    e.target.value = "";
  }

  async function handleDownload(attachment: Attachment) {
    const blob = await downloadAttachment(attachment.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = attachment.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-surface-700 flex items-center gap-2">
          <Paperclip size={16} />
          Attachments
          {attachments.length > 0 && (
            <span className="text-xs font-normal text-surface-400">
              ({attachments.length})
            </span>
          )}
        </h3>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-surface-500 hover:bg-surface-100 hover:text-surface-700"
        >
          <Upload size={14} />
          Upload
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Upload zone */}
      {upload.isPending && (
        <div className="flex items-center gap-2 rounded-lg border border-primary-200 bg-primary-50 p-3">
          <Loader2 size={16} className="animate-spin text-primary-500" />
          <span className="text-sm text-primary-700">Uploading...</span>
        </div>
      )}

      {/* File list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 size={16} className="animate-spin text-surface-400" />
        </div>
      ) : attachments.length === 0 ? (
        <div
          onClick={() => fileInputRef.current?.click()}
          className="cursor-pointer rounded-lg border-2 border-dashed border-surface-200 p-6 text-center hover:border-surface-300"
        >
          <Upload size={24} className="mx-auto text-surface-300" />
          <p className="mt-2 text-sm text-surface-400">
            Click to upload or drag files here
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {attachments.map((attachment) => {
            const Icon = getFileIcon(attachment.mime_type);
            return (
              <div
                key={attachment.id}
                className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-surface-50 group"
              >
                <Icon size={16} className="shrink-0 text-surface-400" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-surface-700 truncate">
                    {attachment.filename}
                  </p>
                  <p className="text-xs text-surface-400">
                    {formatFileSize(attachment.file_size)}
                  </p>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handleDownload(attachment)}
                    className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                  >
                    <Download size={14} />
                  </button>
                  <button
                    onClick={() =>
                      deleteAttach.mutate({
                        taskId,
                        attachmentId: attachment.id,
                      })
                    }
                    className="rounded p-1 text-surface-400 hover:bg-red-50 hover:text-red-500"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
