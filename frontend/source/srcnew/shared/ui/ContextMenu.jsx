import { createPortal } from 'react-dom';

export default function ContextMenu({ x = 0, y = 0, items = [], onClose = () => {} }) {
  return createPortal(
    <div className="context-menu-backdrop" onClick={onClose} onContextMenu={(event) => event.preventDefault()} role="presentation">
      <div
        className="context-menu"
        style={{ left: `${x}px`, top: `${y}px` }}
        onClick={(event) => event.stopPropagation()}
        role="menu"
      >
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            className="context-menu-item"
            disabled={Boolean(item.disabled)}
            onClick={() => {
              if (item.disabled) {
                return;
              }
              item.onSelect?.();
              onClose();
            }}
            role="menuitem"
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>,
    document.body,
  );
}
