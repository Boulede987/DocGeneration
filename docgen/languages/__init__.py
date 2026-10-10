"""Every supported language, by the name entry scripts select it with."""

from docgen.core.language import Language

from .csharp import CSharpLanguage
from .java import JavaLanguage
from .python import PythonLanguage
from .unity import UnityLanguage

REGISTRY: dict[str, Language] = {
    language.name: language
    for language in (JavaLanguage(), CSharpLanguage(), UnityLanguage(), PythonLanguage())
}
