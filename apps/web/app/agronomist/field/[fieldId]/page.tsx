import { Protected } from "@/components/protected";
import { AgronomistFieldPage } from "../../pages";

export default async function AgronomistFieldRoute({ params }: { params: Promise<{ fieldId: string }> }) {
  const { fieldId } = await params;
  return (
    <Protected>
      <AgronomistFieldPage fieldId={fieldId} />
    </Protected>
  );
}
