import { Protected } from "@/components/protected";
import { AnalyticsPage } from "./pages";

export default function AnalyticsRoute() {
  return (
    <Protected>
      <AnalyticsPage />
    </Protected>
  );
}
