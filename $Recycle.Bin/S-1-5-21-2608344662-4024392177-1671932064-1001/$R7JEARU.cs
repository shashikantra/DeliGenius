using System;
using System.Collections.Generic;
using Microsoft.EntityFrameworkCore;

namespace Demo_Project.Models;

public partial class MyCompanyContext : DbContext
{
    public MyCompanyContext()
    {
    }

    public MyCompanyContext(DbContextOptions<MyCompanyContext> options)
        : base(options)
    {
    }

    public virtual DbSet<Employee> Employees { get; set; }

    public virtual DbSet<Manager> Managers { get; set; }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {}

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
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

            entity.HasOne(d => d.Manager).WithMany(p => p.Employees)
                .HasForeignKey(d => d.ManagerId)
                .HasConstraintName("FK_Employee_Manager");
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

        OnModelCreatingPartial(modelBuilder);
    }

    partial void OnModelCreatingPartial(ModelBuilder modelBuilder);
}
