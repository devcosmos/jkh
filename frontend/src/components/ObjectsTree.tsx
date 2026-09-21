import { useState } from "react";
import type { ObjectTreeNode } from "../api/types";

// Организаторы подтвердили: реальных координат объектов не будет — только текущие, теряются
// при демонтаже датчика. Схема вместо карты — их собственная рекомендация (тема 14 в
// "Город 8. ДЖКХ.xlsx - Вопросы_нормализованные_и_Ответы.csv").
const DOT_CLASSES: Record<ObjectTreeNode["aggregated_max_priority"], string> = {
  high: "bg-[#d03b3b]",
  medium: "bg-[#fab219]",
  none: "bg-slate-300",
};

function TreeNode({ node, depth }: { node: ObjectTreeNode; depth: number }) {
  const [open, setOpen] = useState(node.aggregated_max_priority !== "none");
  const hasChildren = node.children.length > 0;

  return (
    <li>
      <div
        className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${
          hasChildren ? "cursor-pointer hover:bg-slate-50" : ""
        }`}
        style={{ paddingLeft: `${depth * 20 + 10}px` }}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >
        <span className="w-3 shrink-0 text-center text-[10px] text-slate-400">
          {hasChildren ? (open ? "▾" : "▸") : ""}
        </span>
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT_CLASSES[node.aggregated_max_priority]}`}
          title={`Открытых рисков в поддереве: ${node.aggregated_open_risk_count}`}
        />
        <span className="truncate font-medium text-slate-800">{node.name}</span>
        {node.kind && <span className="shrink-0 text-sm text-slate-400">{node.kind}</span>}
        {node.aggregated_open_risk_count > 0 && (
          <span className="ml-auto shrink-0 rounded-full bg-red-50 px-2 py-0.5 text-sm font-semibold text-red-600">
            {node.aggregated_open_risk_count}
          </span>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ObjectsTree({ roots }: { roots: ObjectTreeNode[] }) {
  if (!roots.length) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
        Объектов, доступных вам, пока нет.
      </div>
    );
  }
  return (
    <ul className="rounded-2xl border border-slate-200 bg-white p-2">
      {roots.map((node) => (
        <TreeNode key={node.id} node={node} depth={0} />
      ))}
    </ul>
  );
}
