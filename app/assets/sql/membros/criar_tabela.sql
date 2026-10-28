CREATE TABLE membros (
	id Text NOT NULL,
	nome Text NOT NULL,
	data_nascimento DateTime,
	parentesco Number,
	url_foto Text,
	foto_doc_id Text,
	arquivado Text,
CONSTRAINT "unique_id" UNIQUE (id));