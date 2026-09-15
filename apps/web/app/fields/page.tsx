import { Protected } from "@/components/protected";
import { FieldsListPage } from "./pages";

export default function FieldsRoute() {
  return (
    <Protected>
      <FieldsListPage />
    </Protected>
  );
}
