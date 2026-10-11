"""TypeDecl -> PlantUML declaration lines."""

from .model import Member, MemberKind, TypeDecl, TypeKind

STATIC_FLAG = "{static}"
ABSTRACT_FLAG = "{abstract}"
ENUM_STEREOTYPE = "<<enum>>"
INTERFACE_STEREOTYPE = "<<interface>>"
MEMBER_INDENT = "  "


def _render_member(member: Member) -> str:
    flags = [flag for flag, is_set in ((STATIC_FLAG, member.is_static), (ABSTRACT_FLAG, member.is_abstract)) if is_set]
    prefix = " ".join(flags) + " " if flags else ""
    head = f"{member.visibility.value} {prefix}{member.name}"
    if member.kind is MemberKind.METHOD:
        return_suffix = f" : {member.type}" if member.type else ""
        return f"{head}({', '.join(member.params)}){return_suffix}"
    # Languages without mandatory types (Python) can leave a field's type unknown.
    return f"{head} : {member.type}" if member.type else head


def _header(declaration: TypeDecl) -> str:
    if declaration.kind is TypeKind.ENUM:
        return f"enum {declaration.name} {ENUM_STEREOTYPE} {{"
    if declaration.kind is TypeKind.INTERFACE:
        return f"interface {declaration.name} {INTERFACE_STEREOTYPE} {{"
    abstract_prefix = "abstract " if declaration.is_abstract else ""
    stereotype_suffix = f" {declaration.stereotype}" if declaration.stereotype else ""
    return f"{abstract_prefix}class {declaration.name}{stereotype_suffix} {{"


def render_declaration(declaration: TypeDecl) -> list[str]:
    """The declaration's stereotype only applies to classes; enums and
    interfaces always carry their own."""
    if declaration.kind is TypeKind.ENUM:
        body = declaration.enum_values
    else:
        body = [_render_member(member) for member in declaration.members]
    return [_header(declaration)] + [MEMBER_INDENT + line for line in body] + ["}"]
