import { Protected } from "@/components/protected";
import { NewFieldPage } from "../pages";

export default function NewFieldRoute() {
  return (
    <Protected>
      <NewFieldPage />
    </Protected>
  );
}
