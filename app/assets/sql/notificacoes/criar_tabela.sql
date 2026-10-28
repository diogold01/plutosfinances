CREATE TABLE "notificacoes"(
	"id" Text NOT NULL,
	"id_profile" Text NOT NULL,
	"texto" Text NOT NULL,
	"horario" DATETIME,
	"package" Text NOT NULL,
	"tipo" Text,
	"valor" Real,
	"local" Text,
	"ignorar_similares" Text,
	"ignorar_package" Text,
CONSTRAINT "unique_id" UNIQUE ( id ) )
