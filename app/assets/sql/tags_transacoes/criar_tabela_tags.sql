CREATE TABLE "tags"(
	"id" Text NOT NULL,
	"id_profile" Text NOT NULL,
	"nome" Text NOT NULL,
	"cor" Integer,
CONSTRAINT "unique_id" UNIQUE ( id ) )