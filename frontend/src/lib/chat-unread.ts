// Pure rules for unread chat counts: badge text, accessible labels and when a thread may mark itself read.
// Keep this module free of imports so node unit tests can load it.

export const UNREAD_BADGE_CAP = 99;

// Hidden at zero; counts above the cap read "99+" so the badge keeps its size.
export function formatUnreadBadge(count: number): string | undefined {
  if (count <= 0) return undefined;
  return count > UNREAD_BADGE_CAP ? `${UNREAD_BADGE_CAP}+` : String(count);
}

export function unreadAccessibleLabel(count: number): string | undefined {
  if (count <= 0) return undefined;
  return count === 1 ? "1 mensaje sin leer" : `${count} mensajes sin leer`;
}

// A thread is marked read when it is visible and its newest entry differs from the last one marked.
export function shouldMarkChatRead({
  visibility,
  newestEntryId,
  lastMarkedEntryId,
}: {
  visibility: "visible" | "hidden" | "prerender" | "unloaded";
  newestEntryId: string | undefined;
  lastMarkedEntryId: string | undefined;
}): boolean {
  if (visibility !== "visible" || !newestEntryId) return false;
  return newestEntryId !== lastMarkedEntryId;
}
