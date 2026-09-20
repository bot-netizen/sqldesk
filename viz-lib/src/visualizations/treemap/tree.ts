import { toNumber } from "../shared/valueOptions";

/*
  Turning flat rows into the nested tree a treemap draws.

  Kept apart from the drawing so it can be tested on its own: a hierarchy that
  double-counts, or drops a level, produces a treemap that looks entirely
  plausible and is wrong about every proportion on it.
*/

export interface TreeNode {
  name: string;
  /** Only leaves carry a value; a branch is the sum of what is under it. */
  value?: number;
  children?: TreeNode[];
  /** How deep this node sits, root's children being 1. */
  depth: number;
  /** The names from the root down to here, for tooltips and breadcrumbs. */
  path: string[];
}

export interface BuiltTree {
  nodes: TreeNode[];
  /** The sum of every leaf, so a share can be worked out. */
  total: number;
  /** Rows with nothing numeric in the size column. */
  skipped: number;
  /** Rows whose path was empty at every level, and so had nowhere to go. */
  unplaced: number;
}

/** A blank at some level of the path; named rather than dropped. */
export const UNNAMED = "(none)";

function cell(row: any, column: string): string | null {
  const value = row ? row[column] : null;
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return String(value);
}

/**
 * Group rows down the path columns, summing the value column at each leaf.
 *
 * Rows that share a full path are added together rather than drawn twice --
 * a treemap of two rows with the same path is a treemap of one rectangle, and
 * anything else misreports the total.
 */
export default function buildTree(rows: any[], pathColumns: string[], valueColumn: string): BuiltTree {
  const root: TreeNode = { name: "", depth: 0, path: [], children: [] };
  let total = 0;
  let skipped = 0;
  let unplaced = 0;

  (rows || []).forEach((row) => {
    const value = toNumber(row ? row[valueColumn] : null);
    if (value === null || !Number.isFinite(value) || value <= 0) {
      // A treemap divides an area by size: zero and negative have no area to
      // give, and drawing them at all would misstate every other rectangle.
      skipped += 1;
      return;
    }

    const steps = pathColumns.map((column) => cell(row, column));
    if (steps.every((step) => step === null)) {
      unplaced += 1;
      return;
    }

    let node = root;
    steps.forEach((step, level) => {
      const name = step === null ? UNNAMED : step;
      node.children = node.children || [];
      let child = node.children.find((c) => c.name === name);
      if (!child) {
        child = { name, depth: level + 1, path: [...node.path, name] };
        node.children.push(child);
      }
      node = child;
    });

    // The last node on the path is the leaf, and rows sharing it add up.
    node.value = (node.value || 0) + value;
    total += value;
  });

  return { nodes: root.children || [], total, skipped, unplaced };
}

/** How many levels deep the tree actually goes. */
export function treeDepth(nodes: TreeNode[]): number {
  let deepest = 0;
  const walk = (list: TreeNode[]) => {
    list.forEach((node) => {
      deepest = Math.max(deepest, node.depth);
      if (node.children) {
        walk(node.children);
      }
    });
  };
  walk(nodes);
  return deepest;
}
