import { useState } from "react";
import type { ObjectTreeNode } from "../api/types";

// Организаторы подтвердили: реальных координат объектов не будет — только текущие, теряются
// при демонтаже датчика. Схема вместо карты — их собственная рекомендация (тема 14 в
// "Город 8. ДЖКХ.xlsx - Вопросы_нормализованные_и_Ответы.csv").
const PRIORITY_COLOR: Record<ObjectTreeNode["aggregated_max_priority"], string> = {
  high: "var(--danger)",
  medium: "var(--warning)",
  none: "var(--border)",
};

function TreeNode({ node }: { node: ObjectTreeNode }) {
  const [open, setOpen] = useState(node.aggregated_max_priority !== "none");
  const hasChildren = node.children.length > 0;

  return (
    <li className="object-tree-node">
      <div
        className={`object-tree-row${hasChildren ? " clickable" : ""}`}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >
        <span className="object-tree-toggle">{hasChildren ? (open ? "▾" : "▸") : ""}</span>
        <span
          className="object-tree-dot"
          style={{ background: PRIORITY_COLOR[node.aggregated_max_priority] }}
          title={`Открытых рисков в поддереве: ${node.aggregated_open_risk_count}`}
        />
        <span className="object-tree-name">{node.name}</span>
        {node.kind && <span className="object-tree-kind">{node.kind}</span>}
        {node.aggregated_open_risk_count > 0 && (
          <span className="object-tree-count">{node.aggregated_open_risk_count}</span>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ObjectsTree({ roots }: { roots: ObjectTreeNode[] }) {
  if (!roots.length) {
    return <p className="map-footnote">Объектов, доступных вам, пока нет.</p>;
  }
  return (
    <ul className="object-tree">
      {roots.map((node) => (
        <TreeNode key={node.id} node={node} />
      ))}
    </ul>
  );
}
