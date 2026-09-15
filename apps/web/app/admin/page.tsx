import { Protected } from "@/components/protected";
import { AdminPage } from "./pages";

export default function AdminRoute() {
  return (
    <Protected>
      <AdminPage />
    </Protected>
  );
}
