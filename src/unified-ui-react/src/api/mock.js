export async function fetchProposals() {
  await new Promise((r) => setTimeout(r, 250));
  return [
    // { id: "p1", name: "ABC Corp — Q1 Media Plan", updatedAt: "2025-12-10" },
    // { id: "p2", name: "XYZ Group — Premium Package", updatedAt: "2025-12-02" },
  ];
}
