import { expect, test } from "./fixtures";

const NOTES = `# Cell Biology Notes

## Cell structure
Cells are the basic unit of life. The nucleus stores genetic material and the cell membrane controls what enters and leaves the cell.

## Respiration
Mitochondria release energy from glucose through cellular respiration, producing ATP, carbon dioxide and water.

## Genetics
Genes are sections of DNA that code for proteins. Different versions of a gene are called alleles.
`;

test("build a library from a file and a link, search it and generate a cited test", async ({ page }) => {
  await page.goto("/library");
  await expect(page.getByText("Your library is empty")).toBeVisible();

  // Upload a document
  await page.getByTestId("source-file-input").setInputFiles({
    name: "cell-biology.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(NOTES),
  });
  const fileCard = page.getByTestId("source-card").filter({ hasText: "Cell Biology Notes" });
  await expect(fileCard).toBeVisible();
  await expect(fileCard.getByText("Semantic search")).toBeVisible();

  // Add a link (served by the e2e backend)
  await page.getByRole("radio", { name: "Add a link" }).click();
  await page.getByLabel("Web address").fill("http://127.0.0.1:8001/demo/article");
  await page.getByRole("button", { name: "Add link" }).click();
  const linkCard = page.getByTestId("source-card").filter({ hasText: "Photosynthesis basics" });
  await expect(linkCard).toBeVisible();
  await expect(linkCard.getByText("Semantic search")).toBeVisible();

  // A broken link fails with a clear message and can be retried
  await page.getByLabel("Web address").fill("http://127.0.0.1:8001/demo/missing");
  await page.getByRole("button", { name: "Add link" }).click();
  const brokenCard = page.getByTestId("source-card").filter({ hasText: "demo/missing" });
  await expect(brokenCard.getByText("Failed")).toBeVisible();
  await expect(brokenCard).toContainText("HTTP 404");
  await expect(brokenCard.getByRole("button", { name: "Retry" })).toBeVisible();

  // Search inside a source (retrieval preview)
  await fileCard.getByRole("button", { name: /More actions/ }).click();
  await page.getByRole("menuitem", { name: "Search inside" }).click();
  const searchDialog = page.getByRole("dialog");
  await searchDialog.getByLabel("Search query").fill("mitochondria energy");
  await searchDialog.getByRole("button", { name: "Search" }).click();
  await expect(searchDialog.getByTestId("search-hit").first()).toContainText("Mitochondria");
  await searchDialog.getByRole("button", { name: "Close dialog" }).click();

  // Generate from the library with a focus
  await fileCard.getByRole("link", { name: "Generate test" }).click();
  await expect(page).toHaveURL(/\/tests\/new\?source=\d+/);
  await expect(page.getByRole("radio", { name: "Library" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("checkbox", { name: /Cell Biology Notes/ })).toBeChecked();
  await page.getByRole("checkbox", { name: /Photosynthesis basics/ }).check();
  await page.getByLabel("Focus on (optional)").fill("respiration");
  await page.getByLabel("Number of questions").fill("3");
  await page.getByRole("button", { name: "Generate questions" }).click();
  await page.waitForURL(/\/tests\/\d+\/edit$/);
  await expect(page.getByTestId("question-editor")).toHaveCount(3);
  await expect(page.getByLabel("Source reference").first()).toHaveValue(/Cell Biology Notes|Photosynthesis basics/);

  // The citation follows the question into the results
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Test published")).toBeVisible();
  await page.getByRole("link", { name: "View" }).click();
  await page.getByRole("button", { name: "Start test" }).click();
  await expect(page.getByTestId("question-text")).toBeVisible();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Submit test" }).click();
  await page.waitForURL(/\/result$/);
  await expect(page.getByTestId("source-ref").first()).toContainText("Source:");

  // Delete a source
  await page.goto("/library");
  await brokenCard.getByRole("button", { name: /More actions/ }).click();
  await page.getByRole("menuitem", { name: "Delete" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete source" }).click();
  await expect(brokenCard).toHaveCount(0);
});

test("library mode requires a source and explains an empty library", async ({ page, request }) => {
  const sources = (await (await request.get("/api/sources")).json()) as { id: number }[];
  for (const source of sources) await request.delete(`/api/sources/${source.id}`);
  await page.goto("/tests/new");
  await page.getByRole("radio", { name: "Library" }).click();
  await expect(page.getByText("Your library has no ready sources yet")).toBeVisible();
  await page.getByRole("button", { name: "Generate questions" }).click();
  await expect(page).toHaveURL(/\/tests\/new$/);
});
