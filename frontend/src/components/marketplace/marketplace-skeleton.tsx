"use client";

import type { ReactNode } from "react";
import { Skeleton, type SkeletonProps } from "boneyard-js/react";

// Bones use boneyard's compact tuple format: [x%, y_px, w%, h_px, borderRadius].
// Hand-authored layouts stand in until `npx boneyard-js build` captures real ones.
type Bone = [number, number, number, number, number];
type Layout = { name: string; viewportWidth: number; width: number; height: number; bones: Bone[] };

const GRID_GAP_X = 3;
const GRID_GAP_Y = 24;

/** Card grid: each card is a media block followed by title, meta and action lines. */
export function gridLayout(name: string, columns: number, rows: number, cardHeight: number): Layout {
  const cardWidth = (100 - GRID_GAP_X * (columns - 1)) / columns;
  const bones: Bone[] = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const x = column * (cardWidth + GRID_GAP_X);
      const y = row * (cardHeight + GRID_GAP_Y);
      bones.push(
        [x, y, cardWidth, cardHeight - 112, 12],
        [x, y + cardHeight - 100, cardWidth * 0.7, 20, 6],
        [x, y + cardHeight - 72, cardWidth * 0.5, 14, 6],
        [x, y + cardHeight - 46, cardWidth * 0.35, 28, 14],
      );
    }
  }
  const height = rows * cardHeight + (rows - 1) * GRID_GAP_Y;
  return { name, viewportWidth: 1280, width: 1000, height, bones };
}

/** Full-width list rows, each with a title, a meta line and a trailing action. */
export function listLayout(name: string, rows: number, rowHeight: number, gap: number): Layout {
  const bones: Bone[] = [];
  for (let row = 0; row < rows; row += 1) {
    const y = row * (rowHeight + gap);
    bones.push(
      [0, y, 100, rowHeight, 12],
      [2, y + 18, 45, 18, 6],
      [2, y + rowHeight - 34, 30, 14, 6],
      [85, y + rowHeight / 2 - 14, 13, 28, 14],
    );
  }
  const height = rows * rowHeight + (rows - 1) * gap;
  return { name, viewportWidth: 1280, width: 1000, height, bones };
}

/** Provider profile: back link, section nav, hero with avatar, then two content sections. */
export const PROFILE_LAYOUT: Layout = {
  name: "provider-profile",
  viewportWidth: 1280,
  width: 1000,
  height: 420,
  bones: [
    [0, 0, 16, 14, 6],
    [0, 40, 18, 14, 6],
    [0, 72, 18, 14, 6],
    [0, 104, 18, 14, 6],
    [24, 0, 6.4, 64, 32],
    [33, 6, 40, 28, 6],
    [33, 42, 28, 16, 6],
    [33, 66, 20, 16, 6],
    [24, 120, 76, 150, 12],
    [24, 290, 76, 120, 12],
  ],
};

export const SERVICE_RESULTS_LAYOUT = gridLayout("service-results", 3, 6, 240);
export const ROUTE_RESULTS_LAYOUT = gridLayout("route-results", 3, 6, 240);
export const CUSTOMER_SERVICES_LAYOUT = listLayout("customer-services", 4, 84, 12);
export const PROVIDER_REQUESTS_LAYOUT = listLayout("provider-requests", 4, 132, 16);

/** Provider request detail: back link, heading with status, then summary and cargo sections. */
export const PROVIDER_REQUEST_DETAIL_LAYOUT: Layout = {
  name: "provider-request-detail",
  viewportWidth: 1280,
  width: 1000,
  height: 460,
  bones: [
    [0, 0, 18, 14, 6],
    [0, 36, 46, 30, 6],
    [0, 80, 24, 18, 6],
    [0, 120, 100, 150, 12],
    [0, 290, 100, 130, 12],
  ],
};

type MarketplaceSkeletonProps = {
  name: string;
  loading: boolean;
  /** Spanish status text announced to assistive technology while loading. */
  label: string;
  layout: Layout;
  children: ReactNode;
  select?: SkeletonProps["select"];
};

/**
 * Wraps a data-loading region with a boneyard skeleton and a polite live status.
 * The skeleton is hidden from assistive technology; the status text carries the announcement.
 */
export function MarketplaceSkeleton({ name, loading, label, layout, children, select }: MarketplaceSkeletonProps) {
  return (
    <>
      <p aria-live="polite" className="sr-only" role="status">
        {loading ? label : ""}
      </p>
      <div aria-busy={loading} aria-hidden={loading || undefined}>
        <Skeleton initialBones={layout} loading={loading} name={name} select={select}>
          {children}
        </Skeleton>
      </div>
    </>
  );
}
