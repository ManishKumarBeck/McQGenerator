import { createBrowserRouter } from "react-router";
import { AppLayout } from "./components/layout/AppLayout";
import { RouteError } from "./pages/RouteError";
import { CreateTestPage } from "./pages/CreateTestPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EditTestPage } from "./pages/EditTestPage";
import { ExamPage } from "./pages/ExamPage";
import { HistoryPage } from "./pages/HistoryPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ResultPage } from "./pages/ResultPage";
import { TestDetailPage } from "./pages/TestDetailPage";
import { TestsPage } from "./pages/TestsPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "tests", element: <TestsPage /> },
      { path: "tests/new", element: <CreateTestPage /> },
      { path: "tests/new/manual", element: <EditTestPage /> },
      { path: "tests/:testId", element: <TestDetailPage /> },
      { path: "tests/:testId/edit", element: <EditTestPage /> },
      { path: "attempts/:attemptId/result", element: <ResultPage /> },
      { path: "history", element: <HistoryPage /> },
      {
        path: "analytics",
        // Charts are the heaviest dependency, so the analytics page is loaded on demand.
        lazy: async () => ({ Component: (await import("./pages/AnalyticsPage")).AnalyticsPage }),
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
  // The exam runs full-screen, outside the main navigation.
  { path: "attempts/:attemptId", element: <ExamPage />, errorElement: <RouteError /> },
]);
