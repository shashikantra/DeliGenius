using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore;

namespace MyCompany.Models;

public partial class MyCompanyContext : DbContext
{
    public MyCompanyContext()
    {
    }

    public MyCompanyContext(DbContextOptions<MyCompanyContext> options)
        : base(options)
    {
    }

    public virtual DbSet<Country> Countries { get; set; }

    public virtual DbSet<Department> Departments { get; set; }

    public virtual DbSet<Employee> Employees { get; set; }

    public virtual DbSet<EmployeeManager> EmployeeManagers { get; set; }

    public virtual DbSet<JobTitle> JobTitles { get; set; }

    public virtual DbSet<Manager> Managers { get; set; }

    public virtual DbSet<State> States { get; set; }

    public virtual DbSet<StateCountry> StateCountries { get; set; }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    { }

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Country>(entity =>
        {
            entity.ToTable("Country");

            entity.Property(e => e.Country1)
                .HasMaxLength(50)
                .IsUnicode(false)
                .HasColumnName("Country");
        });

        modelBuilder.Entity<Department>(entity =>
        {
            entity.ToTable("Department");

            entity.Property(e => e.Department1)
                .HasMaxLength(50)
                .IsUnicode(false)
                .HasColumnName("Department");
        });

        modelBuilder.Entity<Employee>(entity =>
        {
            entity.ToTable("Employee");

            entity.Property(e => e.Address)
                .HasMaxLength(50)
                .IsUnicode(false);
            entity.Property(e => e.City)
                .HasMaxLength(50)
                .IsUnicode(false);
            entity.Property(e => e.FirstName)
                .HasMaxLength(50)
                .IsUnicode(false);
            entity.Property(e => e.LastName)
                .HasMaxLength(50)
                .IsUnicode(false);

            entity.HasOne(d => d.Department).WithMany(p => p.Employees)
                .HasForeignKey(d => d.DepartmentId)
                .HasConstraintName("FK_Employee_Department");

            entity.HasOne(d => d.JobTitle).WithMany(p => p.Employees)
                .HasForeignKey(d => d.JobTitleId)
                .HasConstraintName("FK_Employee_JobTitle");

            entity.HasOne(d => d.StateCountry).WithMany(p => p.Employees)
                .HasForeignKey(d => d.StateCountryId)
                .HasConstraintName("FK_Employee_StateCountry");
        });

        modelBuilder.Entity<EmployeeManager>(entity =>
        {
            entity.HasKey(e => e.EmployeeManagerId).HasName("PK_EmployeeManger");

            entity.ToTable("EmployeeManager");

            entity.HasOne(d => d.Employee).WithMany(p => p.EmployeeManagers)
                .HasForeignKey(d => d.EmployeeId)
                .HasConstraintName("FK_EmployeeManger_Employee");

            entity.HasOne(d => d.Manager).WithMany(p => p.EmployeeManagers)
                .HasForeignKey(d => d.ManagerId)
                .HasConstraintName("FK_EmployeeManager_Manager");
        });

        modelBuilder.Entity<JobTitle>(entity =>
        {
            entity.ToTable("JobTitle");

            entity.Property(e => e.JobTitle1)
                .HasMaxLength(50)
                .IsUnicode(false)
                .HasColumnName("JobTitle");
        });

        modelBuilder.Entity<Manager>(entity =>
        {
            entity.ToTable("Manager");

            entity.Property(e => e.ManagerFirstName)
                .HasMaxLength(50)
                .IsUnicode(false);
            entity.Property(e => e.ManagerLastName)
                .HasMaxLength(50)
                .IsUnicode(false);
        });

        modelBuilder.Entity<State>(entity =>
        {
            entity.HasKey(e => e.StateId).HasName("PK_Table_1");

            entity.ToTable("State");

            entity.Property(e => e.State1)
                .HasMaxLength(50)
                .IsUnicode(false)
                .HasColumnName("State");
        });

        modelBuilder.Entity<StateCountry>(entity =>
        {
            entity.ToTable("StateCountry");

            entity.HasOne(d => d.Country).WithMany(p => p.StateCountries)
                .HasForeignKey(d => d.CountryId)
                .HasConstraintName("FK_StateCountry_Country");

            entity.HasOne(d => d.State).WithMany(p => p.StateCountries)
                .HasForeignKey(d => d.StateId)
                .HasConstraintName("FK_StateCountry_State");
        });

        OnModelCreatingPartial(modelBuilder);
    }

    partial void OnModelCreatingPartial(ModelBuilder modelBuilder);
}
