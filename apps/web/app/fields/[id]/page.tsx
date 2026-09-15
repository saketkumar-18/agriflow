import { Suspense } from "react";
import { Protected } from "@/components/protected";
import { FieldDetailPage } from "../pages";

export default async function FieldRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <Protected>
        <FieldDetailPage fieldId={id} />
      </Protected>
    </Suspense>
  );
}
