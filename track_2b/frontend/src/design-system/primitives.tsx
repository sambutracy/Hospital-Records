import type { ReactNode } from "react";
import {
  Button as AriaButton,
  Dialog as AriaDialog,
  DialogTrigger,
  Modal,
  ModalOverlay,
  Heading,
} from "react-aria-components";
import type { ButtonProps } from "react-aria-components";
export function Button({
  variant = "primary",
  ...props
}: ButtonProps & { variant?: "primary" | "secondary" | "quiet" }) {
  return <AriaButton {...props} className={`button button--${variant}`} />;
}
export function Notice({
  children,
  tone = "info",
  live = false,
}: {
  children: ReactNode;
  tone?: "info" | "error" | "success" | "warning";
  live?: boolean;
}) {
  return (
    <div
      className={`notice notice--${tone}`}
      role={live ? (tone === "error" ? "alert" : "status") : undefined}
    >
      {children}
    </div>
  );
}
export function Loading({
  children = "Loading your information…",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="state" role="status">
      <span className="loading-mark" aria-hidden="true" />
      {children}
    </div>
  );
}
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function PageHeader({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 tabIndex={-1} id="page-title">
          {title}
        </h1>
        {children && <p>{children}</p>}
      </div>
      {action}
    </header>
  );
}
export function ConfirmDialog({
  trigger,
  title,
  children,
  onConfirm,
  confirmLabel = "Confirm",
  disabled = false,
}: {
  trigger: ReactNode;
  title: string;
  children: ReactNode;
  onConfirm: () => void;
  confirmLabel?: string;
  disabled?: boolean;
}) {
  return (
    <DialogTrigger>
      <Button variant="secondary" isDisabled={disabled}>
        {trigger}
      </Button>
      <ModalOverlay className="modal-overlay">
        <Modal className="modal">
          <AriaDialog>
            {({ close }) => (
              <>
                <Heading slot="title">{title}</Heading>
                {children}
                <div className="actions">
                  <Button variant="secondary" onPress={close}>
                    Cancel
                  </Button>
                  <Button
                    onPress={() => {
                      onConfirm();
                      close();
                    }}
                  >
                    {confirmLabel}
                  </Button>
                </div>
              </>
            )}
          </AriaDialog>
        </Modal>
      </ModalOverlay>
    </DialogTrigger>
  );
}
export function FieldError({
  id,
  children,
}: {
  id: string;
  children?: string;
}) {
  return children ? (
    <p id={id} className="field-error">
      {children}
    </p>
  ) : null;
}
