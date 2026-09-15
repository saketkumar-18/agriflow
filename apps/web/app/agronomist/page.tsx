import { Protected } from "@/components/protected";
import { AgronomistPage } from "./pages";

export default function AgronomistRoute() {
  return (
    <Protected>
      <AgronomistPage />
    </Protected>
  );
}
