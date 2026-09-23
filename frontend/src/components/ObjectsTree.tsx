import { useState } from "react";
import type { ObjectTreeNode } from "../api/types";
import { ChevronIcon } from "./icons";

// Организаторы подтвердили: реальных координат объектов не будет — только текущие, теряются
// при демонтаже датчика. Схема вместо карты — их собственная рекомендация (тема 14 в
// "Город 8. ДЖКХ.xlsx - Вопросы_нормализованные_и_Ответы.csv").
const DOT_CLASSES: Record<ObjectTreeNode["aggregated_max_priority"], string> = {
  high: "bg-[#d03b3b]",
  medium: "bg-[#fab219]",
  none: "bg-slate-300",
};

// Направляющая линия вложенности слева от дочерней группы — в духе Preline tree-view
// (https://preline.co/docs/components/tree-view.html), без их JS/аккордеон-плагина: раскрытие
// уже работает на собственном useState, здесь взята только вёрстка/классы.
function TreeNode({ node, depth }: { node: ObjectTreeNode; depth: number }) {
  const [open, setOpen] = useState(node.aggregated_max_priority !== "none");
  const hasChildren = node.children.length > 0;

  return (
    <li role="treeitem" aria-expanded={hasChildren ? open : undefined}>
      <div className="flex w-full items-center gap-x-0.5 py-0.5">
        <button
          type="button"
          disabled={!hasChildren}
          onClick={() => setOpen((o) => !o)}
          className="flex size-6 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 disabled:pointer-events-none disabled:opacity-0"
          aria-label={open ? "Свернуть" : "Развернуть"}
        >
          <ChevronIcon className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} strokeWidth={2.2} />
        </button>

        <div
          className={`flex min-w-0 grow items-center gap-2.5 rounded-md px-1.5 py-1 text-sm ${
            hasChildren ? "cursor-pointer hover:bg-slate-100" : ""
          }`}
          onClick={() => hasChildren && setOpen((o) => !o)}
        >
          <span
            className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT_CLASSES[node.aggregated_max_priority]}`}
            title={`Открытых рисков в поддереве: ${node.aggregated_open_risk_count}`}
          />
          <span className="truncate font-medium text-slate-800">{node.name}</span>
          {node.kind && <span className="shrink-0 text-sm text-slate-400">{node.kind}</span>}
          {node.aggregated_open_risk_count > 0 && (
            <span className="shrink-0 rounded-full bg-red-50 px-2 py-0.5 text-sm font-semibold text-red-600">
              {node.aggregated_open_risk_count}
            </span>
          )}
        </div>
      </div>
      {hasChildren && open && (
        <ul
          role="group"
          className="relative ms-6 ps-6 before:absolute before:inset-y-0 before:left-3 before:border-s before:border-slate-200"
        >
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
    <ul className="rounded-2xl border border-slate-200 bg-white p-2" role="tree" aria-orientation="vertical">
      {roots.map((node) => (
        <TreeNode key={node.id} node={node} depth={0} />
      ))}
    </ul>
  );
}

/** Сводные цифры по всему дереву для шапки схемы — сколько узлов всего и у скольких
 * есть открытые риски (по своим каналам, не по поддереву — иначе объект-родитель со
 * своими нулём рисков, но рискующим потомком, тоже засчитался бы). */
export function countTreeNodes(roots: ObjectTreeNode[]): { total: number; withOwnRisk: number } {
  let total = 0;
  let withOwnRisk = 0;
  function walk(nodes: ObjectTreeNode[]) {
    for (const n of nodes) {
      total += 1;
      if (n.own_open_risk_count > 0) withOwnRisk += 1;
      walk(n.children);
    }
  }
  walk(roots);
  return { total, withOwnRisk };
}

/** Плоский список узлов с СОБСТВЕННЫМИ открытыми рисками (own_, не aggregated_) — иначе
 * в топе оказались бы только верхнеуровневые объекты, чья агрегированная сумма всегда
 * больше суммы любого потомка. */
export function topRiskyNodes(roots: ObjectTreeNode[], limit = 8): ObjectTreeNode[] {
  const flat: ObjectTreeNode[] = [];
  function walk(nodes: ObjectTreeNode[]) {
    for (const n of nodes) {
      if (n.own_open_risk_count > 0) flat.push(n);
      walk(n.children);
    }
  }
  walk(roots);
  return flat.sort((a, b) => b.own_open_risk_count - a.own_open_risk_count).slice(0, limit);
}
