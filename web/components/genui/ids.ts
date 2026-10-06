// An id usable inside url(#...) and a fragment: anything but letters, digits, "_" and "-" becomes "_". Every component
// builds its anchors from block and citation ids with this, so an id can never put a stray character into a fragment.

export const safeId = (id: string) => id.replace(/[^A-Za-z0-9_-]/g, "_");
