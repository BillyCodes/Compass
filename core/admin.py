"""Admin site: account management and reviewed reference content only.

Per the permission model (blueprint §8.1), administrators manage accounts and
roles but do not get routine access to private student records, so Student,
StudentSkill, MatchResult, ResumeImport and ProgressSnapshot are deliberately
not registered here. Student-pasted job postings are hidden as well.
"""
from django.contrib import admin

from .models import (
    Account,
    CareerProfile,
    CareerRequirement,
    CourseSkill,
    FieldNote,
    JobPosting,
    PostingRequirement,
    Skill,
    UniversityCourse,
)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "status", "created_at")
    list_filter = ("status", "role")
    search_fields = ("email",)
    fields = ("email", "role", "status", "is_staff", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "skill_id")
    list_filter = ("category",)
    search_fields = ("name", "aliases")


class CourseSkillInline(admin.TabularInline):
    model = CourseSkill
    extra = 0


@admin.register(UniversityCourse)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("course_code", "course_name")
    inlines = [CourseSkillInline]


class CareerRequirementInline(admin.TabularInline):
    model = CareerRequirement
    extra = 0


@admin.register(CareerProfile)
class CareerProfileAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "version", "is_published")
    inlines = [CareerRequirementInline]


class PostingRequirementInline(admin.TabularInline):
    model = PostingRequirement
    extra = 0


@admin.register(JobPosting)
class SamplePostingAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "version")
    inlines = [PostingRequirementInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(owner__isnull=True)


@admin.register(FieldNote)
class FieldNoteAdmin(admin.ModelAdmin):
    list_display = ("author_name", "author_role", "author_org", "published_at")
    filter_horizontal = ("skills",)
